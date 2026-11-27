from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from factories import match
from golli.db.matches import upsert_matches
from golli.providers.base import MatchStatus
from golli.services.schedule import FUTURE_DAYS, PAST_DAYS

TASHKENT = ZoneInfo("Asia/Tashkent")
# Shanba, 28-noyabr, Toshkent vaqti bilan 15:00.
NOW = datetime(2026, 11, 28, 15, 0, tzinfo=TASHKENT)
TODAY = date(2026, 11, 28)


async def store(db, *items):
    async with db.begin() as session:
        await upsert_matches(session, "fake", items)


async def test_matches_are_grouped_by_calendar_date(db, schedule):
    await store(
        db,
        match("evening", datetime(2026, 11, 28, 20, 0, tzinfo=TASHKENT)),
        # Yarim tundan keyin boshlanadi: shanba emas, o'z sanasi — yakshanba ro'yxatiga kiradi.
        match("night", datetime(2026, 11, 29, 1, 0, tzinfo=TASHKENT), "Real Madrid", "Barcelona"),
        match("sunday", datetime(2026, 11, 29, 19, 0, tzinfo=TASHKENT), "Liverpool", "Everton"),
    )

    await schedule.rebuild(NOW)

    saturday = await schedule.get_day(TODAY)
    sunday = await schedule.get_day(TODAY + timedelta(days=1))
    assert [(m.home, m.away) for m in saturday] == [("Arsenal", "Manchester City")]
    assert [m.home for m in sunday] == ["Real Madrid", "Liverpool"]
    assert await schedule.get_match_days(NOW) == [TODAY, TODAY + timedelta(days=1)]


async def test_snapshot_carries_score_and_status(db, schedule):
    await store(
        db,
        match(
            "m1",
            datetime(2026, 11, 28, 20, 0, tzinfo=TASHKENT),
            status=MatchStatus.FINISHED,
            score=(2, 1),
            penalties=(4, 3),
        ),
    )

    await schedule.rebuild(NOW)

    [stored] = await schedule.get_day(TODAY)
    assert stored.status is MatchStatus.FINISHED
    assert (stored.home_score, stored.away_score) == (2, 1)
    assert (stored.home_penalties, stored.away_penalties) == (4, 3)
    assert stored.kickoff_at == datetime(2026, 11, 28, 20, 0, tzinfo=TASHKENT)


async def test_window_and_match_days(db, schedule):
    await store(
        db,
        match("too-old", NOW - timedelta(days=PAST_DAYS + 2)),
        match("recent", NOW - timedelta(days=PAST_DAYS), "Liverpool", "Everton"),
        match("far", NOW + timedelta(days=FUTURE_DAYS), "Real Madrid", "Barcelona"),
        match("too-far", NOW + timedelta(days=FUTURE_DAYS + 2)),
    )

    await schedule.rebuild(NOW)

    assert schedule.window(NOW) == (
        TODAY - timedelta(days=PAST_DAYS),
        TODAY + timedelta(days=FUTURE_DAYS),
    )
    assert await schedule.get_match_days(NOW) == [
        TODAY - timedelta(days=PAST_DAYS),
        TODAY + timedelta(days=FUTURE_DAYS),
    ]


async def test_reads_come_from_cache_not_database(db, schedule):
    await store(db, match("m1", datetime(2026, 11, 28, 20, 0, tzinfo=TASHKENT)))
    await schedule.rebuild(NOW)

    # Bazaga keyin qo'shilgan o'yin keshda yo'q: o'qish bazaga bormaganini ko'rsatadi.
    await store(
        db, match("m2", datetime(2026, 11, 28, 22, 0, tzinfo=TASHKENT), "Liverpool", "Everton")
    )

    assert len(await schedule.get_day(TODAY)) == 1
    await schedule.rebuild(NOW)
    assert len(await schedule.get_day(TODAY)) == 2


async def test_empty_cache_falls_back_to_database(db, schedule, redis):
    await store(db, match("m1", datetime(2026, 11, 28, 20, 0, tzinfo=TASHKENT)))
    await schedule.rebuild(NOW)
    await redis.flushall()

    assert [m.home for m in await schedule.get_day(TODAY)] == ["Arsenal"]
    assert await schedule.get_match_days(NOW) == [TODAY]
    # Bazadan olingan nusxa keshga qaytarib qo'yilgan.
    assert await redis.exists(f"golli:day:{TODAY.isoformat()}")


async def test_day_without_matches_is_empty(db, schedule):
    await schedule.rebuild(NOW)

    assert await schedule.get_day(TODAY) == []
    assert await schedule.get_match_days(NOW) == []
