import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from golli.providers.base import MatchStatus, ProviderError
from golli.providers.highlightly import BASE_URL, HighlightlyProvider, parse_match

# Haqiqiy API javoblaridan olingan namunalar.
SAMPLES = json.loads(
    (Path(__file__).parent / "fixtures" / "highlightly" / "matches.json").read_text()
)
PLAN = {"tier": "BASIC", "message": "All data available with current plan."}

# Hujjatdagi "Match states" jadvalining to'liq ro'yxati.
DOCUMENTED_STATES = {
    "Not started": MatchStatus.SCHEDULED,
    "To be announced": MatchStatus.SCHEDULED,
    "Unknown": MatchStatus.SCHEDULED,
    "First half": MatchStatus.LIVE,
    "Second half": MatchStatus.LIVE,
    "Half time": MatchStatus.LIVE,
    "Extra time": MatchStatus.LIVE,
    "Break time": MatchStatus.LIVE,
    "Penalties": MatchStatus.LIVE,
    "In progress": MatchStatus.LIVE,
    "Interrupted": MatchStatus.LIVE,
    "Finished": MatchStatus.FINISHED,
    "Finished after penalties": MatchStatus.FINISHED,
    "Finished after extra time": MatchStatus.FINISHED,
    "Awarded": MatchStatus.FINISHED,
    "Postponed": MatchStatus.POSTPONED,
    "Suspended": MatchStatus.SUSPENDED,
    "Abandoned": MatchStatus.SUSPENDED,
    "Cancelled": MatchStatus.CANCELLED,
}


def page(items: list[dict], total: int, offset: int = 0) -> dict:
    return {
        "data": items,
        "plan": PLAN,
        "pagination": {"totalCount": total, "offset": offset, "limit": 100},
    }


def provider_with(handler) -> HighlightlyProvider:
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return HighlightlyProvider("sinov-kaliti", client=client)


# --- Bitta o'yinni o'qish


def test_not_started_match():
    match = parse_match(SAMPLES["not_started"], "epl")

    assert match.external_id == "1325413711"
    assert match.competition == "epl"
    assert match.season == 2026
    assert match.round == "Regular Season - 12"
    assert match.kickoff_at == datetime(2026, 11, 29, 16, 30, tzinfo=UTC)
    assert match.status is MatchStatus.SCHEDULED
    assert (match.home.external_id, match.home.name) == ("36526", "Arsenal")
    assert (match.away.external_id, match.away.name) == ("43334", "Manchester City")
    assert (match.home_score, match.away_score, match.minute) == (None, None, None)


def test_finished_match():
    match = parse_match(SAMPLES["finished"], "ucl")

    assert match.status is MatchStatus.FINISHED
    assert (match.home_score, match.away_score) == (0, 3)
    assert (match.home_penalties, match.away_penalties) == (None, None)
    # Daqiqa faqat jonli o'yinda saqlanadi.
    assert match.minute is None


def test_match_decided_on_penalties():
    match = parse_match(SAMPLES["penalties"], "ucl")

    assert match.status is MatchStatus.FINISHED
    assert (match.home_score, match.away_score) == (1, 0)
    assert (match.home_penalties, match.away_penalties) == (6, 5)


def test_abandoned_match_is_suspended():
    assert parse_match(SAMPLES["abandoned"], "laliga").status is MatchStatus.SUSPENDED


def test_live_match_keeps_minute():
    raw = json.loads(json.dumps(SAMPLES["not_started"]))
    raw["state"] = {
        "description": "Second half",
        "clock": 67,
        "score": {"current": "3 - 1", "penalties": None},
    }

    match = parse_match(raw, "epl")

    assert match.status is MatchStatus.LIVE
    assert (match.home_score, match.away_score, match.minute) == (3, 1, 67)


@pytest.mark.parametrize(("description", "expected"), DOCUMENTED_STATES.items())
def test_every_documented_state_is_mapped(description, expected):
    raw = json.loads(json.dumps(SAMPLES["finished"]))
    raw["state"]["description"] = description

    assert parse_match(raw, "ucl").status is expected


def test_undocumented_state_is_rejected():
    raw = json.loads(json.dumps(SAMPLES["finished"]))
    raw["state"]["description"] = "Something new"

    with pytest.raises(ValueError):
        parse_match(raw, "ucl")


# --- So'rovlar


async def test_fetch_season_follows_pagination():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        offset = int(request.url.params["offset"])
        items = (
            [SAMPLES["not_started"], SAMPLES["finished"]] if offset == 0 else [SAMPLES["penalties"]]
        )
        return httpx.Response(
            200,
            json=page(items, total=150, offset=offset),
            headers={"x-ratelimit-requests-remaining": str(74 - len(requests))},
        )

    provider = provider_with(handler)
    matches = await provider.fetch_season("epl", 2026)

    assert [m.external_id for m in matches] == ["1325413711", "1391932126", "1354740022"]
    assert [dict(r.url.params) for r in requests] == [
        {"leagueId": "33973", "season": "2026", "limit": "100", "offset": "0"},
        {"leagueId": "33973", "season": "2026", "limit": "100", "offset": "100"},
    ]
    assert all(r.headers["x-rapidapi-key"] == "sinov-kaliti" for r in requests)
    assert all(r.url.path == "/matches" for r in requests)
    assert provider.quota_remaining == 72


async def test_fetch_day_asks_for_date():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=page([SAMPLES["finished"]], total=1))

    matches = await provider_with(handler).fetch_day("ucl", date(2026, 11, 25))

    assert len(matches) == 1
    assert dict(requests[0].url.params) == {
        "leagueId": "2486",
        "date": "2026-11-25",
        "limit": "100",
        "offset": "0",
    }


async def test_broken_item_is_skipped_not_fatal():
    broken = {"id": 1, "state": {"description": "Finished"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page([broken, SAMPLES["finished"]], total=2))

    matches = await provider_with(handler).fetch_day("ucl", date(2026, 11, 25))

    assert [m.external_id for m in matches] == ["1391932126"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"message": "Invalid request token.", "statusCode": 401}),
        httpx.Response(500, json={"message": "Internal server error.", "statusCode": 500}),
        httpx.Response(200, text="<html>bu JSON emas</html>"),
        httpx.Response(200, json={"kutilmagan": "tuzilma"}),
    ],
)
async def test_bad_responses_raise_provider_error(response):
    with pytest.raises(ProviderError):
        await provider_with(lambda request: response).fetch_day("ucl", date(2026, 11, 25))


async def test_network_failure_raises_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ulanib bo'lmadi", request=request)

    with pytest.raises(ProviderError):
        await provider_with(handler).fetch_day("ucl", date(2026, 11, 25))
