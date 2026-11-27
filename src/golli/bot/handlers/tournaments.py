from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from golli.bot import rich_view
from golli.bot.filters import LeagueButton, MenuButton
from golli.bot.keyboards import leagues_menu, main_menu
from golli.bot.replies import answer_rich
from golli.bot.standings_view import render_standings
from golli.bot.states import TournamentsFlow
from golli.db.standings import load_standings
from golli.i18n import Translator
from golli.services.schedule import ScheduleCache
from golli.services.team_names import TeamNames

router = Router(name="tournaments")


@router.message(MenuButton("menu-tournaments"))
async def show_tournaments(message: Message, t: Translator, state: FSMContext) -> None:
    await state.set_state(TournamentsFlow.leagues)
    await state.set_data({})
    await message.answer(t("tournaments-text"), reply_markup=leagues_menu(t))


# Jadval bazadan o'qiladi: uni worker provayderdan olib, yangilab turadi.
@router.message(TournamentsFlow.leagues, LeagueButton())
async def show_standings(
    message: Message,
    bot: Bot,
    competition: str,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    schedule: ScheduleCache,
) -> None:
    rows, updated_at = await load_standings(session, competition)
    text = render_standings(competition, rows, updated_at, t, names, schedule.tz)
    # Klaviatura o'zgarmaydi: foydalanuvchi boshqa turnirni ham tanlay oladi.
    if not rows or updated_at is None:
        await message.answer(text, reply_markup=leagues_menu(t))
        return
    rich = rich_view.standings_message(competition, rows, updated_at, t, names, schedule.tz)
    await answer_rich(bot, message, rich, fallback=text, reply_markup=leagues_menu(t))


@router.message(TournamentsFlow.leagues, MenuButton("menu-back"))
async def back_to_main_menu(message: Message, t: Translator, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("menu-main"), reply_markup=main_menu(t))


@router.message(TournamentsFlow.leagues, F.text)
async def ask_to_choose(message: Message, t: Translator) -> None:
    await message.answer(t("choose-hint"), reply_markup=leagues_menu(t))
