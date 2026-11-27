import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import func, select

from factories import FakeProvider, match, standing
from golli.db.matches import upsert_matches
from golli.db.models import Standing, Team
from golli.db.standings import load_standings, replace_standings
from golli.providers.base import MatchStatus, ProviderError
from golli.providers.highlightly import HighlightlyProvider
from golli.services.sync import STANDINGS_DELAY, Syncer

SAMPLES = json.loads(
    (Path(__file__).parent / "fixtures" / "highlightly" / "standings.json").read_text()
)
TASHKENT = ZoneInfo("Asia/Tashkent")
NOW = datetime(2026, 11, 28, 10, 0, tzinfo=TASHKENT)
ALL = [("ucl", 2026), ("epl", 2026), ("laliga", 2026)]


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TASHKENT)


def provider_with(handler) -> HighlightlyProvider:
    client = httpx.AsyncClient(
        base_url="https://soccer.highlightly.net", transport=httpx.MockTransport(handler)
    )
    return HighlightlyProvider("sinov-kaliti", client=client)


# --- Provayder


async def test_standings_are_parsed_from_real_response():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json=SAMPLES["epl"], headers={"x-ratelimit-requests-remaining": "80"}
        )

    provider = provider_with(handler)
    rows = await provider.fetch_standings("epl", 2026)

    assert [(r.position, r.team.name, r.points) for r in rows[:2]] == [
        (1, "Arsenal", 28),
        (2, "Brighton", 22),
    ]
    first = rows[0]
    assert (first.played, first.wins, first.draws, first.losses) == (11, 9, 1, 1)
    assert (first.goals_for, first.goals_against) == (17, 7)
    assert first.team.external_id == "36526"
    assert first.team.logo_url == "https://highlightly.net/soccer/images/teams/36526.png"
    # Bitta jadvalli turnirda guruh nomi kerak emas.
    assert {row.group for row in rows} == {None}
    assert requests[0].url.path == "/standings"
    assert dict(requests[0].url.params) == {"leagueId": "33973", "season": "2026"}
    assert provider.quota_remaining == 80


async def test_row_without_home_and_away_split_is_accepted():
    provider = provider_with(lambda request: httpx.Response(200, json=SAMPLES["ucl"]))

    rows = await provider.fetch_standings("ucl", 2026)

    assert (rows[-1].position, rows[-1].team.name, rows[-1].points) == (36, "Slovan Bratislava", 0)


async def test_several_groups_keep_their_names():
    payload = {
        "groups": [
            {"name": "Group A", "standings": SAMPLES["epl"]["groups"][0]["standings"][:1]},
            {"name": "Group B", "standings": SAMPLES["epl"]["groups"][0]["standings"][1:2]},
        ]
    }
    provider = provider_with(lambda request: httpx.Response(200, json=payload))

    rows = await provider.fetch_standings("ucl", 2026)

    assert [(row.group, row.team.name) for row in rows] == [
        ("Group A", "Arsenal"),
        ("Group B", "Brighton"),
    ]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, text="Too many requests"),
        httpx.Response(200, json={"message": "nimadir"}),
        httpx.Response(200, json={"groups": [{"name": "X", "standings": [{"position": 1}]}]}),
        httpx.Response(200, text="<html>"),
    ],
)
async def test_bad_standings_response_raises_provider_error(response):
    provider = provider_with(lambda request: response)

    with pytest.raises(ProviderError):
        await provider.fetch_standings("epl", 2026)


# --- Baza


async def save(db, competition: str, *rows, season: int = 2026, now: datetime = NOW) -> None:
    async with db.begin() as session:
        await replace_standings(session, "fake", competition, season, rows, now)


async def table(db, competition: str):
    async with db() as session:
        return await load_standings(session, competition)


async def test_table_is_stored_and_read_in_order(db):
    await save(
        db,
        "epl",
        standing(2, "Manchester City", 22, goals=(20, 9)),
        standing(1, "Arsenal", 25, goals=(18, 4)),
    )

    rows, updated_at = await table(db, "epl")

    assert [(r.position, r.team, r.points, r.goal_difference) for r in rows] == [
        (1, "Arsenal", 25, 14),
        (2, "Manchester City", 22, 11),
    ]
    assert (rows[0].played, rows[0].wins, rows[0].draws, rows[0].losses) == (10, 8, 1, 1)
    assert updated_at == NOW
    assert await table(db, "laliga") == ([], None)


async def test_new_table_replaces_the_old_one(db):
    await save(db, "epl", standing(1, "Arsenal", 25), standing(2, "Everton", 20))
    later = NOW + timedelta(hours=5)

    await save(db, "epl", standing(1, "Liverpool", 27), standing(2, "Arsenal", 26), now=later)

    rows, updated_at = await table(db, "epl")
    assert [(r.position, r.team, r.points) for r in rows] == [
        (1, "Liverpool", 27),
        (2, "Arsenal", 26),
    ]
    assert updated_at == later
    async with db() as session:
        assert await session.scalar(select(func.count()).select_from(Standing)) == 2


async def test_empty_answer_keeps_the_last_known_table(db):
    await save(db, "epl", standing(1, "Arsenal", 25))

    await save(db, "epl")

    rows, _ = await table(db, "epl")
    assert [r.team for r in rows] == ["Arsenal"]


async def test_table_reuses_clubs_known_from_matches(db):
    async with db.begin() as session:
        await upsert_matches(session, "fake", [match("m1", NOW)])
        team = await session.scalar(select(Team).where(Team.name == "Arsenal"))
        team.emoji_id = "5001"

    await save(db, "epl", standing(1, "Arsenal", 25))

    rows, _ = await table(db, "epl")
    assert rows[0].team_emoji == "5001"
    async with db() as session:
        assert await session.scalar(select(func.count()).select_from(Team)) == 2


async def test_latest_season_wins(db):
    await save(db, "epl", standing(1, "Everton", 80), season=2025)
    await save(db, "epl", standing(1, "Arsenal", 25), season=2026)

    rows, _ = await table(db, "epl")

    assert [r.team for r in rows] == ["Arsenal"]


# --- Fon yangilanishi


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def syncer(provider, db, schedule, redis, settings) -> Syncer:
    return Syncer(provider, db, schedule, redis, settings.tz)


async def test_first_tick_loads_every_table(syncer, provider, db):
    provider.standings["epl"] = [standing(1, "Arsenal", 25), standing(2, "Everton", 20)]

    await syncer.tick(at(28, 10))

    assert provider.standings_calls == ALL
    rows, updated_at = await table(db, "epl")
    assert [r.team for r in rows] == ["Arsenal", "Everton"]
    assert updated_at == at(28, 10)


async def test_tables_are_not_requested_again_without_a_reason(syncer, provider):
    await syncer.tick(at(28, 10))
    provider.standings_calls.clear()

    await syncer.tick(at(28, 10, 1))
    await syncer.tick(at(28, 23))
    await syncer.tick(at(29, 5, 59))

    assert provider.standings_calls == []


async def test_tables_are_refreshed_once_a_day_in_the_morning(syncer, provider):
    await syncer.tick(at(28, 10))
    provider.standings_calls.clear()

    await syncer.tick(at(29, 6, 1))

    assert provider.standings_calls == ALL


async def test_table_is_refreshed_after_its_match_has_finished(syncer, provider, db):
    kickoff = at(28, 20)
    provider.season["epl"] = [match("m1", kickoff)]
    await syncer.tick(at(28, 10))
    provider.standings_calls.clear()

    # O'yin tugadi, lekin provayder jadvalni yangilashiga hali vaqt berilmagan.
    provider.set_day(match("m1", kickoff, status=MatchStatus.FINISHED, score=(2, 1)))
    await syncer.tick(kickoff + timedelta(minutes=105))
    await syncer.tick(kickoff + STANDINGS_DELAY - timedelta(minutes=1))
    assert provider.standings_calls == []

    provider.standings["epl"] = [standing(1, "Arsenal", 28)]
    await syncer.tick(kickoff + STANDINGS_DELAY)
    # Faqat shu turnir jadvali: boshqalarida o'yin bo'lmagan.
    assert provider.standings_calls == [("epl", 2026)]
    assert [r.points for r in (await table(db, "epl"))[0]] == [28]

    await syncer.tick(kickoff + STANDINGS_DELAY + timedelta(minutes=1))
    assert len(provider.standings_calls) == 1


async def test_failed_table_request_is_retried_only_after_delay(syncer, provider):
    await syncer.tick(at(28, 10))
    provider.standings_calls.clear()

    provider.fail = True
    await syncer.tick(at(29, 6, 30))
    assert provider.standings_calls == [("ucl", 2026)]
    await syncer.tick(at(29, 6, 40))
    assert len(provider.standings_calls) == 1

    provider.fail = False
    await syncer.tick(at(29, 7, 1))
    assert provider.standings_calls == [("ucl", 2026), *ALL]


async def test_last_table_time_survives_restart(provider, db, schedule, redis, settings):
    await Syncer(provider, db, schedule, redis, settings.tz).tick(at(28, 10))
    provider.standings_calls.clear()

    await Syncer(provider, db, schedule, redis, settings.tz).tick(at(28, 11))

    assert provider.standings_calls == []


def test_now_is_utc_aware():
    # Jadval vaqti vaqt mintaqasi bilan saqlanadi: ko'rsatishda Toshkent vaqtiga o'giriladi.
    assert NOW.astimezone(UTC).hour == 5
