from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from golli.services.days import current_season, day_bounds, football_day

TASHKENT = ZoneInfo("Asia/Tashkent")


def tashkent(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TASHKENT)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (tashkent(28, 17, 30), date(2026, 11, 28)),  # shanba kechqurun
        (tashkent(29, 1, 0), date(2026, 11, 28)),  # yarim tundan keyingi o'yin — hali shanba
        (tashkent(29, 5, 59), date(2026, 11, 28)),
        (tashkent(29, 6, 0), date(2026, 11, 29)),  # 06:00 da yangi kun boshlanadi
    ],
)
def test_football_day_starts_at_six(moment, expected):
    assert football_day(moment, TASHKENT) == expected


def test_football_day_accepts_utc_moment():
    # 20:00 UTC = Toshkentda ertasi kuni 01:00 — oldingi futbol kuniga kiradi.
    assert football_day(datetime(2026, 11, 25, 20, 0, tzinfo=UTC), TASHKENT) == date(2026, 11, 25)


def test_day_bounds_cover_exactly_one_football_day():
    start, end = day_bounds(date(2026, 11, 28), TASHKENT)

    assert start == tashkent(28, 6)
    assert end == tashkent(29, 6)
    assert football_day(start, TASHKENT) == date(2026, 11, 28)
    assert football_day(end - timedelta(seconds=1), TASHKENT) == date(2026, 11, 28)
    assert football_day(end, TASHKENT) == date(2026, 11, 29)


@pytest.mark.parametrize(
    ("moment", "season"),
    [
        (datetime(2026, 11, 26, tzinfo=UTC), 2026),
        (datetime(2027, 3, 1, tzinfo=UTC), 2026),
        (datetime(2027, 6, 30, tzinfo=UTC), 2026),
        (datetime(2027, 7, 1, tzinfo=UTC), 2027),
    ],
)
def test_current_season(moment, season):
    assert current_season(moment) == season
