"""Testlar uchun tayyor ma'lumot yasovchilar."""

from datetime import UTC, date, datetime

from aiogram.methods import SendRichMessage
from aiogram.types import InputRichBlockTable, InputRichMessage, RichTextCustomEmoji

from golli.providers.base import MatchData, MatchStatus, ProviderError, StandingData, TeamData

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
        # Jadval so'rovlari alohida yoziladi: o'yinlar bo'yicha so'rovlar tartibini buzmasin.
        self.standings: dict[str, list[StandingData]] = {}
        self.standings_calls: list[tuple[str, int]] = []
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

    async def fetch_standings(self, competition: str, season: int) -> list[StandingData]:
        self.standings_calls.append((competition, season))
        if self.fail:
            raise ProviderError("sinov xatosi")
        return self.standings.get(competition, [])


def standing(
    position: int, name: str, points: int, *, played: int = 10, goals=(15, 5)
) -> StandingData:
    """Jadval qatori: g'alaba/durang/mag'lubiyatlar ochkoga mos qilib to'ldiriladi."""
    wins, draws = divmod(points, 3)
    return StandingData(
        team=team(name),
        position=position,
        played=played,
        wins=wins,
        draws=draws,
        losses=played - wins - draws,
        goals_for=goals[0],
        goals_against=goals[1],
        points=points,
    )


# --- Jadvalli (rich) xabarlarni testda o'qish


def _inline(text) -> str:
    """Kataklar va sarlavhalardagi matn; maxsus emoji (logotip) "<identifikator>" ko'rinishida."""
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        return "".join(_inline(part) for part in text)
    if isinstance(text, RichTextCustomEmoji):
        return f"<{text.custom_emoji_id}>"
    return _inline(text.text)


def rich_lines(rich: InputRichMessage) -> list[str]:
    """Jadvalli xabar satrlari: sarlavha "### matn", jadval qatori "katak | katak | katak"."""
    lines = []
    for block in rich.blocks:
        if isinstance(block, InputRichBlockTable):
            lines += [" | ".join(_inline(cell.text) for cell in row) for row in block.cells]
        elif hasattr(block, "size"):
            lines.append(f"{'#' * block.size} {_inline(block.text)}")
        else:
            lines.append(_inline(block.text))
    return lines


def text_of(request) -> str:
    """Bot yuborgan xabar matni: oddiy xabarniki ham, jadvalli xabarniki ham."""
    if isinstance(request, SendRichMessage):
        return "\n".join(rich_lines(request.rich_message))
    return request.text
