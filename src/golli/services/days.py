"""“Futbol kuni”: soat 06:00 dan ertasi 06:00 gacha (bot vaqt mintaqasida).

Yevropa o'yinlarining ko'pi Toshkent vaqti bilan yarim tundan keyin boshlanadi.
Muxlis uchun shanba kechasi 01:00 dagi o'yin — "bugungi" o'yin, shuning uchun
00:00–06:00 oralig'idagi o'yinlar oldingi kunga tegishli deb hisoblanadi.
"""

from datetime import date, datetime, time, timedelta, tzinfo

DAY_START_HOUR = 6


def football_day(moment: datetime, tz: tzinfo) -> date:
    return (moment.astimezone(tz) - timedelta(hours=DAY_START_HOUR)).date()


def day_bounds(day: date, tz: tzinfo) -> tuple[datetime, datetime]:
    """Futbol kunining boshi (kiradi) va oxiri (kirmaydi)."""
    start = datetime.combine(day, time(DAY_START_HOUR), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(DAY_START_HOUR), tzinfo=tz)
    return start, end


def current_season(moment: datetime) -> int:
    """Mavsum boshlangan yil. Yevropa mavsumlari iyulda almashadi: 2026/27 -> 2026."""
    return moment.year if moment.month >= 7 else moment.year - 1
