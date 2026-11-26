from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from factories import FakeProvider, match
from golli.providers.base import MatchStatus
from golli.services.schedule import MATCH_DAYS_KEY
from golli.services.sync import Syncer, poll_due

TASHKENT = ZoneInfo("Asia/Tashkent")
SATURDAY = date(2026, 11, 28)
SEASON_CALLS = [("season", "ucl", 2026), ("season", "epl", 2026), ("season", "laliga", 2026)]


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TASHKENT)


def minutes(value: int) -> timedelta:
    return timedelta(minutes=value)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def syncer(provider, db, schedule, redis, settings) -> Syncer:
    return Syncer(provider, db, schedule, redis, settings.tz)


def day_calls(provider: FakeProvider) -> list[tuple]:
    return [call for call in provider.calls if call[0] == "day"]


# --- Mavsum taqvimi


async def test_first_tick_syncs_whole_season_and_fills_cache(syncer, provider, schedule):
    provider.season["epl"] = [match("m1", at(28, 20))]

    await syncer.tick(at(28, 10))

    assert provider.calls == SEASON_CALLS
    assert [m.home for m in await schedule.get_day(SATURDAY)] == ["Arsenal"]
    assert await schedule.get_match_days(at(28, 10)) == [SATURDAY]


async def test_season_is_synced_once_per_football_day(syncer, provider):
    await syncer.tick(at(28, 10))
    provider.calls.clear()

    await syncer.tick(at(28, 23))
    await syncer.tick(at(29, 5, 59))
    assert provider.calls == []

    # 06:00 da yangi futbol kuni boshlanadi.
    await syncer.tick(at(29, 6, 1))
    assert provider.calls == SEASON_CALLS


async def test_failed_season_sync_is_retried_only_after_delay(syncer, provider):
    provider.fail = True
    await syncer.tick(at(28, 10))
    assert provider.calls == SEASON_CALLS[:1]

    await syncer.tick(at(28, 10, 10))
    assert len(provider.calls) == 1

    provider.fail = False
    await syncer.tick(at(28, 10, 31))
    assert provider.calls == SEASON_CALLS[:1] + SEASON_CALLS


async def test_last_sync_time_survives_restart(provider, db, schedule, redis, settings):
    await Syncer(provider, db, schedule, redis, settings.tz).tick(at(28, 10))
    provider.calls.clear()

    restarted = Syncer(provider, db, schedule, redis, settings.tz)
    await restarted.tick(at(28, 11))

    assert provider.calls == []


async def test_unattended_match_triggers_catch_up_sync(syncer, provider, schedule):
    kickoff = at(28, 17)
    provider.season["epl"] = [match("m1", kickoff)]
    await syncer.tick(at(28, 6, 30))
    provider.calls.clear()

    # Worker o'yin paytida ishlamagan: o'yin 5,5 soat oldin boshlangan, bazada hanuz "scheduled".
    provider.season["epl"] = [match("m1", kickoff, status=MatchStatus.FINISHED, score=(1, 1))]
    await syncer.tick(at(28, 22, 30))

    assert provider.calls == SEASON_CALLS
    [stored] = await schedule.get_day(SATURDAY)
    assert (stored.status, stored.home_score, stored.away_score) == (MatchStatus.FINISHED, 1, 1)

    await syncer.tick(at(28, 22, 31))
    assert provider.calls == SEASON_CALLS


# --- Bugungi o'yinlar holati


async def test_match_is_polled_at_checkpoints_then_until_it_ends(syncer, provider, schedule):
    kickoff = at(28, 20)  # 15:00 UTC
    provider.season["epl"] = [match("m1", kickoff)]
    await syncer.tick(at(28, 10))

    # Boshlanguncha va dastlabki daqiqalarda so'rov yo'q.
    await syncer.tick(kickoff - minutes(1))
    await syncer.tick(kickoff + minutes(5))
    assert day_calls(provider) == []

    # 10-daqiqa: boshlanganini tasdiqlash.
    provider.set_day(match("m1", kickoff, status=MatchStatus.LIVE, score=(0, 0), minute=10))
    await syncer.tick(kickoff + minutes(10))
    assert day_calls(provider) == [("day", "epl", SATURDAY)]
    for minute in (11, 30, 54):
        await syncer.tick(kickoff + minutes(minute))
    assert len(day_calls(provider)) == 1

    # 55-daqiqa: tanaffusdagi hisob; kesh ham yangilanadi.
    provider.set_day(match("m1", kickoff, status=MatchStatus.LIVE, score=(1, 0), minute=45))
    await syncer.tick(kickoff + minutes(55))
    assert len(day_calls(provider)) == 2
    [live] = await schedule.get_day(SATURDAY)
    assert (live.status, live.home_score, live.away_score) == (MatchStatus.LIVE, 1, 0)

    # 105-daqiqadan boshlab har 3 daqiqada, o'yin tugaguncha.
    await syncer.tick(kickoff + minutes(104))
    assert len(day_calls(provider)) == 2
    await syncer.tick(kickoff + minutes(105))
    await syncer.tick(kickoff + minutes(106))
    await syncer.tick(kickoff + minutes(107))
    assert len(day_calls(provider)) == 3

    provider.set_day(match("m1", kickoff, status=MatchStatus.FINISHED, score=(2, 1)))
    await syncer.tick(kickoff + minutes(108))
    assert len(day_calls(provider)) == 4
    [final] = await schedule.get_day(SATURDAY)
    assert (final.status, final.home_score, final.away_score) == (MatchStatus.FINISHED, 2, 1)

    # Tugagan o'yin uchun boshqa so'rov ketmaydi.
    await syncer.tick(kickoff + minutes(111))
    await syncer.tick(kickoff + minutes(140))
    assert len(day_calls(provider)) == 4


async def test_each_competition_is_polled_separately(syncer, provider):
    kickoff = at(28, 20)
    provider.season["epl"] = [match("e1", kickoff)]
    provider.season["laliga"] = [
        match("l1", kickoff, "Real Madrid", "Barcelona", competition="laliga")
    ]
    await syncer.tick(at(28, 10))

    await syncer.tick(kickoff + minutes(10))

    assert sorted(day_calls(provider)) == [("day", "epl", SATURDAY), ("day", "laliga", SATURDAY)]


async def test_matches_sharing_kickoff_cost_one_request(syncer, provider):
    kickoff = at(28, 20)
    provider.season["epl"] = [
        match("m1", kickoff),
        match("m2", kickoff, "Liverpool", "Everton"),
    ]
    await syncer.tick(at(28, 10))

    await syncer.tick(kickoff + minutes(10))

    assert len(day_calls(provider)) == 1


async def test_failed_poll_is_not_repeated_every_minute(syncer, provider):
    kickoff = at(28, 20)
    provider.season["epl"] = [match("m1", kickoff)]
    await syncer.tick(at(28, 10))

    provider.fail = True
    await syncer.tick(kickoff + minutes(10))
    await syncer.tick(kickoff + minutes(11))
    await syncer.tick(kickoff + minutes(12))

    assert len(day_calls(provider)) == 1


async def test_cache_window_moves_at_day_change_even_if_provider_is_down(syncer, provider, redis):
    await syncer.tick(at(28, 10))
    await redis.delete(MATCH_DAYS_KEY)

    provider.fail = True
    await syncer.tick(at(29, 6, 1))

    assert await redis.exists(MATCH_DAYS_KEY)


# --- poll_due


KICKOFF = at(28, 20)


@pytest.mark.parametrize(
    ("elapsed", "since_last_poll", "expected"),
    [
        (5, None, False),  # hali erta
        (10, None, True),  # birinchi nuqta
        (30, 20, False),  # birinchi nuqta bajarilgan, ikkinchisi hali kelmagan
        (30, None, True),  # worker qayta ishga tushgan: o'tkazib yuborilgan nuqta bajariladi
        (55, 45, True),  # ikkinchi nuqta
        (80, 25, False),
        (105, 50, True),  # tugash bosqichi boshlandi
        (107, 2, False),
        (108, 3, True),
        (140, 3, False),  # kech bosqich: har 5 daqiqada
        (140, 5, True),
    ],
)
def test_poll_due(elapsed, since_last_poll, expected):
    now = KICKOFF + minutes(elapsed)
    last_poll = None if since_last_poll is None else now - minutes(since_last_poll)

    assert poll_due(now, [KICKOFF], last_poll) is expected


def test_poll_due_with_no_matches():
    assert poll_due(KICKOFF, [], None) is False
