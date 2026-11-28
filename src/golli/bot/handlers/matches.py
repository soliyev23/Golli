from datetime import UTC, date, datetime, timedelta

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from golli.bot import rich_view
from golli.bot.callbacks import DayCallback, UpcomingCallback
from golli.bot.filters import MenuButton
from golli.bot.keyboards import main_menu
from golli.bot.replies import answer_rich
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


Days = list[tuple[date, list[DayMatch]]]


async def upcoming_days(schedule: ScheduleCache, now: datetime) -> Days:
    """ "Yaqin o'yinlar": hali tugamagan o'yinlari bor eng yaqin ikki kun.

    Tugagan o'yin bu ro'yxatdan darhol chiqadi va "Oxirgi o'yinlar"da ko'rinadi. Barcha
    o'yinlari tugagan kun (masalan, bugun) butunlay tushib qoladi, o'rniga keyingi o'yin kuni.
    """
    today = schedule.today(now)
    first = await _first_day(schedule, today, now)
    days: Days = []
    for day in await schedule.get_match_days(now):
        if day < first:
            continue
        pending = [m for m in await schedule.get_day(day) if m.status is not MatchStatus.FINISHED]
        if pending:
            days.append((day, pending))
        if len(days) == UPCOMING_DAYS:
            break
    return days


async def recent_days(schedule: ScheduleCache, now: datetime) -> Days:
    """ "Oxirgi o'yinlar": o'yin tugagan eng oxirgi kun va undan oldingisi, yangisi tepada.

    Xuddi "Yaqin o'yinlar" qoidasi, faqat orqaga qarab: o'yinsiz kunlar tashlab ketiladi.
    """
    today = schedule.today(now)
    past_days = [day for day in await schedule.get_match_days(now) if day <= today]
    days: Days = []
    for day in reversed(past_days):
        matches = await schedule.get_day(day)
        if any(match.status is MatchStatus.FINISHED for match in matches):
            days.append((day, [m for m in matches if m.status not in NOT_PLAYED_YET]))
        if len(days) == RECENT_DAYS:
            break
    return days


async def upcoming_text(
    schedule: ScheduleCache, now: datetime, t: Translator, names: TeamNames
) -> str:
    """ "Yaqin o'yinlar" oddiy matnda (jadvalli xabar o'tmagan holat va eski tugmalar uchun)."""
    days = await upcoming_days(schedule, now)
    if not days:
        return render_no_upcoming(t)
    return render_days(days, today=schedule.today(now), now=now, t=t, names=names, tz=schedule.tz)


async def _send_days(
    bot: Bot,
    message: Message,
    days: Days,
    empty_text: str,
    schedule: ScheduleCache,
    now: datetime,
    t: Translator,
    names: TeamNames,
) -> None:
    """Kunlar ro'yxatini jadvalli xabar qilib yuboradi; o'yin bo'lmasa — qisqa matn."""
    if not days:
        await message.answer(empty_text, reply_markup=main_menu(t))
        return
    layout = {"today": schedule.today(now), "now": now, "t": t, "names": names, "tz": schedule.tz}
    await answer_rich(
        bot,
        message,
        rich_view.days_message(days, **layout),
        fallback=render_days(days, **layout),
        reply_markup=main_menu(t),
    )


# Javob bilan birga menyu ham yuboriladi: eski klaviaturali foydalanuvchida yangi tugmalar
# shu tariqa paydo bo'ladi.


@router.message(MenuButton("menu-matches"))
async def show_upcoming(
    message: Message, bot: Bot, t: Translator, schedule: ScheduleCache, names: TeamNames
) -> None:
    now = datetime.now(UTC)
    days = await upcoming_days(schedule, now)
    await _send_days(bot, message, days, render_no_upcoming(t), schedule, now, t, names)


@router.message(MenuButton("menu-recent"))
async def show_recent(
    message: Message, bot: Bot, t: Translator, schedule: ScheduleCache, names: TeamNames
) -> None:
    now = datetime.now(UTC)
    days = await recent_days(schedule, now)
    await _send_days(bot, message, days, render_no_recent(t), schedule, now, t, names)


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
