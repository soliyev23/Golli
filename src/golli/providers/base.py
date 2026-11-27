"""Futbol ma'lumotlari provayderi uchun umumiy interfeys.

Loyihaning qolgan qismi faqat shu fayldagi turlarni biladi. Provayderni almashtirish
uchun FootballProvider'ni amalga oshiruvchi yangi adapter yozish kifoya.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"  # boshqa kunga ko'chirilgan
    SUSPENDED = "suspended"  # boshlanib, to'xtatilgan
    CANCELLED = "cancelled"


class ProviderError(Exception):
    """Provayderdan ma'lumot olib bo'lmadi (tarmoq, limit, noto'g'ri javob)."""


@dataclass(frozen=True, slots=True)
class TeamData:
    external_id: str
    name: str
    logo_url: str | None = None


@dataclass(frozen=True, slots=True)
class MatchData:
    external_id: str
    competition: str  # golli.competitions dagi kod
    season: int  # mavsum boshlangan yil: 2026/27 uchun 2026
    round: str | None
    kickoff_at: datetime  # vaqt mintaqasi bilan (UTC)
    status: MatchStatus
    minute: int | None  # faqat jonli o'yinda
    home: TeamData
    away: TeamData
    home_score: int | None = None
    away_score: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None


@dataclass(frozen=True, slots=True)
class StandingData:
    """Turnir jadvalining bitta qatori."""

    team: TeamData
    position: int
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    points: int
    # Turnir bir nechta guruhga bo'lingan bo'lsa — guruh nomi.
    group: str | None = None


class FootballProvider(Protocol):
    name: str

    async def fetch_season(self, competition: str, season: int) -> list[MatchData]:
        """Turnirning butun mavsumdagi o'yinlari."""
        ...

    async def fetch_day(self, competition: str, day: date) -> list[MatchData]:
        """Turnirning berilgan UTC sanasida boshlanadigan o'yinlari, joriy hisobi bilan."""
        ...

    async def fetch_standings(self, competition: str, season: int) -> list[StandingData]:
        """Turnirning joriy jadvali, o'rinlar tartibida."""
        ...
