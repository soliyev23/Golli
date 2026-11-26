from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from golli.db.models import ExternalRef, Match, Team
from golli.providers.base import MatchData, MatchStatus

# Hali yakuniy holatga kelmagan o'yinlar.
UNFINISHED = (MatchStatus.SCHEDULED.value, MatchStatus.LIVE.value)


@dataclass(slots=True)
class UpsertResult:
    created: int = 0
    updated: int = 0
    teams_created: int = 0


async def _load_refs(
    session: AsyncSession, provider: str, entity: str, external_ids: set[str]
) -> dict[str, int]:
    rows = await session.execute(
        select(ExternalRef.external_id, ExternalRef.internal_id).where(
            ExternalRef.provider == provider,
            ExternalRef.entity == entity,
            ExternalRef.external_id.in_(external_ids),
        )
    )
    return {external_id: internal_id for external_id, internal_id in rows}


def _match_fields(data: MatchData, team_ids: dict[str, int]) -> dict[str, object]:
    return {
        "competition": data.competition,
        "season": data.season,
        "round": data.round,
        "home_team_id": team_ids[data.home.external_id],
        "away_team_id": team_ids[data.away.external_id],
        "kickoff_at": data.kickoff_at,
        "status": data.status.value,
        "minute": data.minute,
        "home_score": data.home_score,
        "away_score": data.away_score,
        "home_penalties": data.home_penalties,
        "away_penalties": data.away_penalties,
    }


async def upsert_matches(
    session: AsyncSession, provider: str, items: Sequence[MatchData]
) -> UpsertResult:
    """Provayderdan kelgan o'yinlarni bazaga yozadi: yangisini qo'shadi, o'zgarganini yangilaydi."""
    result = UpsertResult()
    if not items:
        return result

    # Klublar
    teams = {team.external_id: team for item in items for team in (item.home, item.away)}
    team_ids = await _load_refs(session, provider, "team", set(teams))
    known_teams = {
        team.id: team
        for team in await session.scalars(select(Team).where(Team.id.in_(team_ids.values())))
    }
    for external_id, data in teams.items():
        internal_id = team_ids.get(external_id)
        if internal_id is None:
            team = Team(name=data.name)
            session.add(team)
            await session.flush()
            session.add(
                ExternalRef(
                    provider=provider, entity="team", external_id=external_id, internal_id=team.id
                )
            )
            team_ids[external_id] = team.id
            result.teams_created += 1
        elif known_teams[internal_id].name != data.name:
            known_teams[internal_id].name = data.name

    # O'yinlar
    match_ids = await _load_refs(session, provider, "match", {item.external_id for item in items})
    known_matches = {
        match.id: match
        for match in await session.scalars(select(Match).where(Match.id.in_(match_ids.values())))
    }
    created: list[tuple[str, Match]] = []
    for item in items:
        fields = _match_fields(item, team_ids)
        internal_id = match_ids.get(item.external_id)
        if internal_id is None:
            match = Match(**fields)
            session.add(match)
            created.append((item.external_id, match))
            # Javobda bir o'yin ikki marta kelsa (sahifalar siljisa), ikkinchisi tashlab ketiladi.
            match_ids[item.external_id] = -1
            continue
        match = known_matches.get(internal_id)
        if match is None:
            continue
        changed = {name: value for name, value in fields.items() if getattr(match, name) != value}
        for name, value in changed.items():
            setattr(match, name, value)
        result.updated += bool(changed)

    await session.flush()
    session.add_all(
        ExternalRef(provider=provider, entity="match", external_id=external_id, internal_id=m.id)
        for external_id, m in created
    )
    result.created = len(created)
    return result


async def unfinished_kickoffs(
    session: AsyncSession, after: datetime, until: datetime
) -> list[tuple[str, datetime]]:
    """Tugamagan o'yinlar (turnir, boshlanish vaqti): `after` < boshlanish <= `until`."""
    rows = await session.execute(
        select(Match.competition, Match.kickoff_at).where(
            Match.status.in_(UNFINISHED),
            Match.kickoff_at > after,
            Match.kickoff_at <= until,
        )
    )
    return [(competition, kickoff_at) for competition, kickoff_at in rows]


async def has_unfinished(session: AsyncSession, after: datetime, until: datetime) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(
                    Match.status.in_(UNFINISHED),
                    Match.kickoff_at > after,
                    Match.kickoff_at <= until,
                )
            )
        )
    )
