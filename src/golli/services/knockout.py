"""Pley-off o'yinlari: bosqich, ikki o'yin yig'indisi va keyingi bosqichga chiqqan klub."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from golli.competitions import KNOCKOUT_STAGES, TWO_LEGGED_STAGES, knockout_stage
from golli.db.models import Match
from golli.providers.base import MatchStatus
from golli.services.schedule import DayMatch, load_matches

Side = Literal["home", "away"]


def stage_of(match: DayMatch) -> str | None:
    """Pley-off bosqichi kodi ("playoff", "round16", ...); liga o'yini uchun None."""
    return knockout_stage(match.competition, match.round)


def aggregate_of(match: DayMatch) -> tuple[int, int] | None:
    """Ikki o'yin yig'indisi (uy egasi, mehmon) — faqat javob o'yinida.

    O'yin hali boshlanmagan bo'lsa, yig'indi birinchi o'yin hisobiga teng.
    """
    if match.first_leg_home is None or match.first_leg_away is None:
        return None
    return (
        match.first_leg_home + (match.home_score or 0),
        match.first_leg_away + (match.away_score or 0),
    )


def advancing_side(match: DayMatch) -> Side | None:
    """Tugagan pley-off o'yinidan keyin keyingi bosqichga chiqqan (finalda — g'olib) tomon.

    Birinchi o'yinda, liga o'yinida yoki g'olib aniqlanmagan bo'lsa — None.
    """
    stage = stage_of(match)
    if stage is None or match.status is not MatchStatus.FINISHED:
        return None
    if match.home_score is None or match.away_score is None:
        return None
    if stage in TWO_LEGGED_STAGES:
        total = aggregate_of(match)
        if total is None:
            return None
    else:
        total = (match.home_score, match.away_score)
    if total[0] == total[1]:
        # Yig'indi teng: g'olibni penaltilar seriyasi aniqlaydi.
        if match.home_penalties is None or match.away_penalties is None:
            return None
        total = (match.home_penalties, match.away_penalties)
    if total[0] == total[1]:
        return None
    return "home" if total[0] > total[1] else "away"


@dataclass(frozen=True, slots=True)
class Tie:
    """Pley-off juftligi: ikki o'yinli bosqichda ikkala o'yin, finalda bitta o'yin."""

    stage: str
    # Birinchi (yoki yagona) o'yin: juftlik shu o'yinning mezboni va mehmoni tartibida ko'rsatiladi.
    first: DayMatch
    # Javob o'yini; hali taqvimga qo'yilmagan yoki bosqich bir o'yinli bo'lsa None.
    second: DayMatch | None = None


def build_ties(matches: list[DayMatch]) -> list[Tie]:
    """Pley-off o'yinlarini juftliklarga yig'adi (birinchi o'yin vaqti tartibida)."""
    legs: dict[tuple[str, frozenset[int]], list[DayMatch]] = {}
    for match in sorted(matches, key=lambda m: (m.kickoff_at, m.id)):
        stage = stage_of(match)
        if stage is not None:
            legs.setdefault((stage, frozenset((match.home_id, match.away_id))), []).append(match)
    return [
        Tie(stage, group[0], group[1] if len(group) > 1 else None)
        for (stage, _), group in legs.items()
    ]


async def load_ties(session: AsyncSession, competition: str) -> list[Tie]:
    """Turnirning joriy (bazadagi eng so'nggi) mavsumidagi pley-off juftliklari."""
    rounds = list(KNOCKOUT_STAGES.get(competition, {}))
    if not rounds:
        return []
    latest_season = (
        select(func.max(Match.season)).where(Match.competition == competition).scalar_subquery()
    )
    matches = await load_matches(
        session,
        Match.competition == competition,
        Match.season == latest_season,
        Match.round.in_(rounds),
    )
    return build_ties(matches)
