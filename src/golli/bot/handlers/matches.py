from datetime import UTC, date, datetime, timedelta

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from golli.bot.callbacks import DayCallback, UpcomingCallback
from golli.bot.filters import MenuButton
from golli.bot.keyboards import main_menu
from golli.bot.views import is_live, render_days, render_no_recent, render_no_upcoming
from golli.i18n import Translator
from golli.providers.base import MatchStatus
from golli.services.schedule import DayMatch, ScheduleCache
from golli.services.team_names import TeamNames

router = Router(name="matches")

# Har bir ro'yxatda nechta o'yin kuni ko'rsatiladi; o'yinsiz kunlar tashlab ketiladi.
UPCOMING_DAYS = 2
RECENT_DAYS = 2
# Kecha boshlangan o'yin shu vaqt ichida hali tugamagan bo'lsa, ro'yxat kechagi kundan boshlanadi.
CARRY_OVER = timedelta(hours=4)
# Hali natijasi yo'q o'yinlar: ular "Oxirgi o'yinlar"da emas, "Yaqin o'yinlar"da turadi.
NOT_PLAYED_YET = (MatchStatus.SCHEDULED, MatchStatus.LIVE)


async def _first_day(schedule: ScheduleCache, today: date, now: datetime) -> date:
    """Odatda bugun. Yarim tundan o'tib ketgan o'yin davom etayotgan bo'lsa — kecha."""
    yesterday = today - timedelta(days=1)
    in_play = any(
        is_live(match, now) and now - match.kickoff_at < CARRY_OVER
        for match in await schedule.get_day(yesterday)
    )
    return yesterday if in_play else today


async def upcoming_text(
    schedule: ScheduleCache, now: datetime, t: Translator, names: TeamNames
) -> str:
    """ "Yaqin o'yinlar": eng yaqin o'yin kuni (bugun o'yin bo'lsa — bugun) va undan keyingisi."""
    today = schedule.today(now)
    first = await _first_day(schedule, today, now)
    shown = [day for day in await schedule.get_match_days(now) if day >= first][:UPCOMING_DAYS]
    if not shown:
        return render_no_upcoming(t)
    days = [(day, await schedule.get_day(day)) for day in shown]
    return render_days(days, today=today, now=now, t=t, names=names, tz=schedule.tz)


async def recent_text(
    schedule: ScheduleCache, now: datetime, t: Translator, names: TeamNames
) -> str:
    """ "Oxirgi o'yinlar": o'yin tugagan eng oxirgi kun va undan oldingisi, yangisi tepada.

    Xuddi "Yaqin o'yinlar" qoidasi, faqat orqaga qarab: o'yinsiz kunlar tashlab ketiladi.
    """
    today = schedule.today(now)
    past_days = [day for day in await schedule.get_match_days(now) if day <= today]
    days: list[tuple[date, list[DayMatch]]] = []
    for day in reversed(past_days):
        matches = await schedule.get_day(day)
        if any(match.status is MatchStatus.FINISHED for match in matches):
            days.append((day, [m for m in matches if m.status not in NOT_PLAYED_YET]))
        if len(days) == RECENT_DAYS:
            break
    if not days:
        return render_no_recent(t)
    return render_days(days, today=today, now=now, t=t, names=names, tz=schedule.tz)


# Javob bilan birga menyu ham yuboriladi: eski klaviaturali foydalanuvchida yangi tugmalar
# shu tariqa paydo bo'ladi.


@router.message(MenuButton("menu-matches"))
async def show_upcoming(
    message: Message, t: Translator, schedule: ScheduleCache, names: TeamNames
) -> None:
    text = await upcoming_text(schedule, datetime.now(UTC), t, names)
    await message.answer(text, reply_markup=main_menu(t))


@router.message(MenuButton("menu-recent"))
async def show_recent(
    message: Message, t: Translator, schedule: ScheduleCache, names: TeamNames
) -> None:
    text = await recent_text(schedule, datetime.now(UTC), t, names)
    await message.answer(text, reply_markup=main_menu(t))


# Avval ro'yxat ostida kundan kunga o'tish tugmalari bo'lgan. Eski xabarda qolgan shunday
# tugma bosilsa, xabar hozirgi "Yaqin o'yinlar" ro'yxatiga almashtiriladi va tugmalari olinadi.
@router.callback_query(DayCallback.filter())
@router.callback_query(UpcomingCallback.filter())
async def retire_old_buttons(
    callback: CallbackQuery, t: Translator, schedule: ScheduleCache, names: TeamNames
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    text = await upcoming_text(schedule, datetime.now(UTC), t, names)
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except TelegramBadRequest as exc:
        # Matn o'zgarmagan bo'lsa Telegram xato qaytaradi — bu holatda qiladigan ish yo'q.
        if "message is not modified" not in str(exc):
            raise
