from datetime import UTC, date, datetime
from typing import Any

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from golli.bot.callbacks import DayCallback, UpcomingCallback
from golli.bot.filters import MenuButton
from golli.bot.views import day_navigation, render_days, render_no_upcoming
from golli.i18n import Translator
from golli.services.schedule import ScheduleCache
from golli.services.team_names import TeamNames

router = Router(name="matches")

# "Yaqin o'yinlar" bosilganda nechta o'yin kuni ko'rsatiladi.
UPCOMING_DAYS = 2


async def _upcoming_view(
    schedule: ScheduleCache, now: datetime, t: Translator, names: TeamNames
) -> dict[str, Any]:
    """Eng yaqin o'yin kuni (bugun o'yin bo'lsa — bugun) va undan keyingi o'yin kuni."""
    today = schedule.today(now)
    match_days = await schedule.get_match_days(now)
    shown = [day for day in match_days if day >= today][:UPCOMING_DAYS]
    if not shown:
        return {
            "text": render_no_upcoming(t),
            "reply_markup": day_navigation(today, today, match_days, t, back_to_upcoming=False),
        }
    days = [(day, await schedule.get_day(day)) for day in shown]
    return {
        "text": render_days(days, today=today, now=now, t=t, names=names, tz=schedule.tz),
        "reply_markup": day_navigation(shown[0], shown[-1], match_days, t, back_to_upcoming=False),
    }


async def _day_view(
    schedule: ScheduleCache, day: date, now: datetime, t: Translator, names: TeamNames
) -> dict[str, Any]:
    days = [(day, await schedule.get_day(day))]
    return {
        "text": render_days(
            days, today=schedule.today(now), now=now, t=t, names=names, tz=schedule.tz
        ),
        "reply_markup": day_navigation(
            day, day, await schedule.get_match_days(now), t, back_to_upcoming=True
        ),
    }


async def _edit(callback: CallbackQuery, view: dict[str, Any]) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(**view)
    except TelegramBadRequest as exc:
        # Matn o'zgarmagan bo'lsa Telegram xato qaytaradi — bu holatda qiladigan ish yo'q.
        if "message is not modified" not in str(exc):
            raise


@router.message(MenuButton("menu-matches"))
async def show_upcoming(
    message: Message, t: Translator, schedule: ScheduleCache, names: TeamNames
) -> None:
    await message.answer(**await _upcoming_view(schedule, datetime.now(UTC), t, names))


@router.callback_query(UpcomingCallback.filter())
async def back_to_upcoming(
    callback: CallbackQuery, t: Translator, schedule: ScheduleCache, names: TeamNames
) -> None:
    await _edit(callback, await _upcoming_view(schedule, datetime.now(UTC), t, names))


@router.callback_query(DayCallback.filter())
async def show_day(
    callback: CallbackQuery,
    callback_data: DayCallback,
    t: Translator,
    schedule: ScheduleCache,
    names: TeamNames,
) -> None:
    now = datetime.now(UTC)
    first, last = schedule.window(now)
    try:
        day = date.fromisoformat(callback_data.day)
    except ValueError:
        day = None
    if day is None or not first <= day <= last:
        # Eski xabardagi tugma: u ko'rsatgan kun endi oynadan tashqarida.
        view = await _upcoming_view(schedule, now, t, names)
    else:
        view = await _day_view(schedule, day, now, t, names)
    await _edit(callback, view)
