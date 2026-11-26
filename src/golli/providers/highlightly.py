"""Highlightly Football API adapteri (https://highlightly.net/football-api/documentation/)."""

import logging
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

import httpx

from golli.providers.base import MatchData, MatchStatus, ProviderError, TeamData

logger = logging.getLogger(__name__)

BASE_URL = "https://soccer.highlightly.net"
PAGE_SIZE = 100

LEAGUE_IDS: Mapping[str, int] = {"ucl": 2486, "epl": 33973, "laliga": 119924}

# Hujjatda sanab o'tilgan barcha state.description qiymatlari.
_STATUSES: Mapping[str, MatchStatus] = {
    "Not started": MatchStatus.SCHEDULED,
    "To be announced": MatchStatus.SCHEDULED,
    "Unknown": MatchStatus.SCHEDULED,
    "First half": MatchStatus.LIVE,
    "Half time": MatchStatus.LIVE,
    "Second half": MatchStatus.LIVE,
    "Extra time": MatchStatus.LIVE,
    "Break time": MatchStatus.LIVE,
    "Penalties": MatchStatus.LIVE,
    "In progress": MatchStatus.LIVE,
    "Interrupted": MatchStatus.LIVE,
    "Finished": MatchStatus.FINISHED,
    "Finished after extra time": MatchStatus.FINISHED,
    "Finished after penalties": MatchStatus.FINISHED,
    "Awarded": MatchStatus.FINISHED,
    "Postponed": MatchStatus.POSTPONED,
    "Suspended": MatchStatus.SUSPENDED,
    "Abandoned": MatchStatus.SUSPENDED,
    "Cancelled": MatchStatus.CANCELLED,
}


def _parse_score(raw: str | None) -> tuple[int | None, int | None]:
    """ "2 - 1" -> (2, 1); hisob yo'q bo'lsa (None, None)."""
    if not raw:
        return None, None
    home, away = raw.split("-")
    return int(home), int(away)


def parse_match(raw: Mapping[str, Any], competition: str) -> MatchData:
    state = raw["state"]
    status = _STATUSES.get(state["description"])
    if status is None:
        raise ValueError(f"noma'lum holat: {state['description']!r}")
    home_score, away_score = _parse_score(state["score"].get("current"))
    home_penalties, away_penalties = _parse_score(state["score"].get("penalties"))
    return MatchData(
        external_id=str(raw["id"]),
        competition=competition,
        season=int(raw["league"]["season"]),
        round=raw.get("round"),
        kickoff_at=datetime.fromisoformat(raw["date"]),
        status=status,
        minute=state.get("clock") if status is MatchStatus.LIVE else None,
        home=TeamData(str(raw["homeTeam"]["id"]), raw["homeTeam"]["name"]),
        away=TeamData(str(raw["awayTeam"]["id"]), raw["awayTeam"]["name"]),
        home_score=home_score,
        away_score=away_score,
        home_penalties=home_penalties,
        away_penalties=away_penalties,
    )


class HighlightlyProvider:
    name = "highlightly"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=BASE_URL, timeout=20)
        self._headers = {"x-rapidapi-key": api_key}
        # Oxirgi javobdagi kunlik limit qoldig'i; hali so'rov bo'lmagan bo'lsa None.
        self.quota_remaining: int | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_season(self, competition: str, season: int) -> list[MatchData]:
        return await self._fetch_matches(competition, {"season": season})

    async def fetch_day(self, competition: str, day: date) -> list[MatchData]:
        return await self._fetch_matches(competition, {"date": day.isoformat()})

    async def _fetch_matches(self, competition: str, query: dict[str, Any]) -> list[MatchData]:
        params = {"leagueId": LEAGUE_IDS[competition], **query, "limit": PAGE_SIZE}
        matches: list[MatchData] = []
        offset = 0
        while True:
            payload = await self._get("/matches", {**params, "offset": offset})
            for raw in payload["data"]:
                try:
                    matches.append(parse_match(raw, competition))
                except (KeyError, TypeError, ValueError) as exc:
                    # Bitta buzuq yozuv butun sinxronizatsiyani to'xtatmasin.
                    logger.warning("O'yin o'tkazib yuborildi (id=%s): %r", raw.get("id"), exc)
            offset += PAGE_SIZE
            if not payload["data"] or offset >= payload["pagination"]["totalCount"]:
                return matches

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Highlightly'ga ulanib bo'lmadi: {exc!r}") from exc

        remaining = response.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None and remaining.isdigit():
            self.quota_remaining = int(remaining)

        if response.status_code != httpx.codes.OK:
            raise ProviderError(
                f"Highlightly {response.status_code} qaytardi "
                f"(limit qoldig'i: {self.quota_remaining}): {response.text[:200]}"
            )
        try:
            payload = response.json()
            if not isinstance(payload["data"], list):
                raise TypeError("data ro'yxat emas")
            int(payload["pagination"]["totalCount"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"Highlightly javobi kutilgan tuzilmada emas: {exc!r}") from exc

        plan_message = (payload.get("plan") or {}).get("message", "")
        if plan_message and "All data available" not in plan_message:
            logger.warning("Highlightly tarif ogohlantirishi: %s", plan_message)
        return payload
