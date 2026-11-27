"""Testlar uchun tayyor ma'lumot yasovchilar."""

from datetime import UTC, date, datetime

from golli.providers.base import MatchData, MatchStatus, ProviderError, TeamData

# Soxta Telegram (conftest.RecordingSession) botga shu username'ni beradi.
BOT_USERNAME = "golli_test_bot"

# Nom -> provayder ID'si. Nomlar data/team_names.toml dagi kalitlar bilan bir xil.
TEAM_IDS = {
    "Arsenal": "36526",
    "Manchester City": "43334",
    "Liverpool": "34824",
    "Everton": "40000",
    "Real Madrid": "461175",
    "Barcelona": "450000",
    "Club Brugge KV": "485003",
}


def logo_url(name: str) -> str:
    return f"https://logos.test/{TEAM_IDS.get(name, name).replace(' ', '-')}.png"


def team(name: str) -> TeamData:
    return TeamData(external_id=TEAM_IDS.get(name, f"x-{name}"), name=name, logo_url=logo_url(name))


def match(
    external_id: str,
    kickoff_at: datetime,
    home: str = "Arsenal",
    away: str = "Manchester City",
    *,
    competition: str = "epl",
    status: MatchStatus = MatchStatus.SCHEDULED,
    score: tuple[int, int] | None = None,
    penalties: tuple[int, int] | None = None,
    minute: int | None = None,
    round: str | None = "Regular Season - 12",
    season: int = 2026,
) -> MatchData:
    return MatchData(
        external_id=external_id,
        competition=competition,
        season=season,
        round=round,
        kickoff_at=kickoff_at,
        status=status,
        minute=minute,
        home=team(home),
        away=team(away),
        home_score=score[0] if score else None,
        away_score=score[1] if score else None,
        home_penalties=penalties[0] if penalties else None,
        away_penalties=penalties[1] if penalties else None,
    )


class FakeProvider:
    """Xotiradagi provayder: nima qaytarishi testda belgilanadi, so'rovlari yozib boriladi."""

    name = "fake"

    def __init__(self) -> None:
        self.season: dict[str, list[MatchData]] = {}
        self.days: dict[tuple[str, date], list[MatchData]] = {}
        self.calls: list[tuple] = []
        self.fail = False

    def set_day(self, *items: MatchData) -> None:
        """O'yinlarni fetch_day javobiga qo'yadi (turnir va UTC sana bo'yicha)."""
        for item in items:
            key = (item.competition, item.kickoff_at.astimezone(UTC).date())
            self.days[key] = [
                m for m in self.days.get(key, []) if m.external_id != item.external_id
            ]
            self.days[key].append(item)

    async def fetch_season(self, competition: str, season: int) -> list[MatchData]:
        self.calls.append(("season", competition, season))
        if self.fail:
            raise ProviderError("sinov xatosi")
        return self.season.get(competition, [])

    async def fetch_day(self, competition: str, day: date) -> list[MatchData]:
        self.calls.append(("day", competition, day))
        if self.fail:
            raise ProviderError("sinov xatosi")
        return self.days.get((competition, day), [])
