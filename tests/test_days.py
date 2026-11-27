from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from golli.services.days import current_season, day_bounds, local_date

TASHKENT = ZoneInfo("Asia/Tashkent")


def tashkent(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TASHKENT)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (tashkent(28, 17, 30), date(2026, 11, 28)),  # shanba kechqurun
        (tashkent(28, 23, 59), date(2026, 11, 28)),
        (tashkent(29, 0, 0), date(2026, 11, 29)),  # yarim tunda yangi kun boshlanadi
        (tashkent(29, 1, 0), date(2026, 11, 29)),  # tungi o'yin — o'z sanasida, yakshanba
    ],
)
def test_day_follows_the_calendar(moment, expected):
    assert local_date(moment, TASHKENT) == expected


def test_local_date_accepts_utc_moment():
    # 20:00 UTC = Toshkentda ertasi kuni 01:00.
    assert local_date(datetime(2026, 11, 25, 20, 0, tzinfo=UTC), TASHKENT) == date(2026, 11, 26)


def test_day_bounds_cover_exactly_one_calendar_day():
    start, end = day_bounds(date(2026, 11, 28), TASHKENT)

    assert start == tashkent(28, 0)
    assert end == tashkent(29, 0)
    assert local_date(start, TASHKENT) == date(2026, 11, 28)
    assert local_date(end - timedelta(seconds=1), TASHKENT) == date(2026, 11, 28)
    assert local_date(end, TASHKENT) == date(2026, 11, 29)


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
