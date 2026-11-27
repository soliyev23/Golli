"""Kunlar taqvim bo'yicha, bot vaqt mintaqasida: 00:00 dan 24:00 gacha.

O'yin qaysi sanada boshlansa, o'sha kunga tegishli: Toshkent vaqti bilan yakshanba
01:00 dagi o'yin shanba ro'yxatida emas, yakshanba ro'yxatida turadi.
"""

from datetime import date, datetime, time, timedelta, tzinfo


def local_date(moment: datetime, tz: tzinfo) -> date:
    return moment.astimezone(tz).date()


def day_bounds(day: date, tz: tzinfo) -> tuple[datetime, datetime]:
    """Kunning boshi (kiradi) va oxiri (kirmaydi)."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start, end


def current_season(moment: datetime) -> int:
    """Mavsum boshlangan yil. Yevropa mavsumlari iyulda almashadi: 2026/27 -> 2026."""
    return moment.year if moment.month >= 7 else moment.year - 1
