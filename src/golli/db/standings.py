"""Turnir jadvallari: provayderdan kelgan jadvalni saqlash va o'qish."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from golli.db.matches import upsert_teams
from golli.db.models import Standing, Team
from golli.providers.base import StandingData


@dataclass(frozen=True, slots=True)
class StandingRow:
    """Jadvalning ko'rsatishga tayyor qatori: klub nomi va logotipi bilan."""

    position: int
    team: str
    team_emoji: str | None
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    points: int
    group: str | None

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


async def replace_standings(
    session: AsyncSession,
    provider: str,
    competition: str,
    season: int,
    rows: Sequence[StandingData],
    now: datetime,
) -> None:
    """Turnir jadvalini butunligicha yangisiga almashtiradi.

    Bo'sh javob jadvalni o'chirmaydi: provayder vaqtincha hech narsa qaytarmasa,
    foydalanuvchi oxirgi ma'lum jadvalni ko'raveradi.
    """
    if not rows:
        return
    team_ids, _ = await upsert_teams(
        session, provider, {row.team.external_id: row.team for row in rows}
    )
    await session.execute(
        delete(Standing).where(Standing.competition == competition, Standing.season == season)
    )
    session.add_all(
        Standing(
            competition=competition,
            season=season,
            team_id=team_ids[row.team.external_id],
            group_name=row.group,
            position=row.position,
            played=row.played,
            wins=row.wins,
            draws=row.draws,
            losses=row.losses,
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            points=row.points,
            updated_at=now,
        )
        for row in rows
    )


async def load_standings(
    session: AsyncSession, competition: str
) -> tuple[list[StandingRow], datetime | None]:
    """Turnirning eng so'nggi mavsumdagi jadvali va u yangilangan vaqt (jadval yo'q bo'lsa None)."""
    latest_season = (
        select(func.max(Standing.season))
        .where(Standing.competition == competition)
        .scalar_subquery()
    )
    result = await session.execute(
        select(Standing, Team.name, Team.emoji_id)
        .join(Team, Team.id == Standing.team_id)
        .where(Standing.competition == competition, Standing.season == latest_season)
        .order_by(Standing.group_name.nulls_first(), Standing.position, Team.name)
    )
    rows: list[StandingRow] = []
    updated_at: datetime | None = None
    for standing, team_name, team_emoji in result:
        updated_at = standing.updated_at
        rows.append(
            StandingRow(
                position=standing.position,
                team=team_name,
                team_emoji=team_emoji,
                played=standing.played,
                wins=standing.wins,
                draws=standing.draws,
                losses=standing.losses,
                goals_for=standing.goals_for,
                goals_against=standing.goals_against,
                points=standing.points,
                group=standing.group_name,
            )
        )
    return rows, updated_at
