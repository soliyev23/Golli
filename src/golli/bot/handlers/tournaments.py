from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from golli.bot import rich_view
from golli.bot.filters import LeagueButton, MenuButton
from golli.bot.keyboards import leagues_menu, main_menu, sections_menu
from golli.bot.replies import answer_rich
from golli.bot.standings_view import render_knockout, render_standings
from golli.bot.states import TournamentsFlow
from golli.competitions import KNOCKOUT_STAGES
from golli.db.standings import load_standings
from golli.i18n import Translator
from golli.services.knockout import load_ties
from golli.services.schedule import ScheduleCache
from golli.services.team_names import TeamNames

router = Router(name="tournaments")


@router.message(MenuButton("menu-tournaments"))
async def show_tournaments(message: Message, t: Translator, state: FSMContext) -> None:
    await state.set_state(TournamentsFlow.leagues)
    await state.set_data({})
    await message.answer(t("tournaments-text"), reply_markup=leagues_menu(t))


async def _send_table(
    bot: Bot,
    message: Message,
    competition: str,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    schedule: ScheduleCache,
    reply_markup: ReplyKeyboardMarkup,
) -> None:
    """Turnir jadvali. Bazadan o'qiladi: uni worker provayderdan olib, yangilab turadi."""
    rows, updated_at = await load_standings(session, competition)
    text = render_standings(competition, rows, updated_at, t, names, schedule.tz)
    if not rows or updated_at is None:
        await message.answer(text, reply_markup=reply_markup)
        return
    rich = rich_view.standings_message(competition, rows, updated_at, t, names, schedule.tz)
    await answer_rich(bot, message, rich, fallback=text, reply_markup=reply_markup)


@router.message(TournamentsFlow.leagues, LeagueButton())
async def choose_league(
    message: Message,
    bot: Bot,
    competition: str,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    schedule: ScheduleCache,
    state: FSMContext,
) -> None:
    if competition in KNOCKOUT_STAGES:
        # Pley-off bosqichi bor turnir: avval nimani ko'rsatish so'raladi.
        await state.set_state(TournamentsFlow.sections)
        await state.set_data({"competition": competition})
        league = t(f"competition-{competition}")
        await message.answer(
            t("tournaments-sections-text", league=league), reply_markup=sections_menu(t)
        )
        return
    # Klaviatura o'zgarmaydi: foydalanuvchi boshqa turnirni ham tanlay oladi.
    await _send_table(bot, message, competition, session, t, names, schedule, leagues_menu(t))


async def _chosen(state: FSMContext) -> str | None:
    competition = (await state.get_data()).get("competition")
    return competition if competition in KNOCKOUT_STAGES else None


@router.message(TournamentsFlow.sections, MenuButton("menu-table"))
async def show_table(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    schedule: ScheduleCache,
    state: FSMContext,
) -> None:
    competition = await _chosen(state)
    if competition is None:
        await show_tournaments(message, t, state)
        return
    await _send_table(bot, message, competition, session, t, names, schedule, sections_menu(t))


@router.message(TournamentsFlow.sections, MenuButton("menu-knockout"))
async def show_knockout(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    schedule: ScheduleCache,
    state: FSMContext,
) -> None:
    competition = await _chosen(state)
    if competition is None:
        await show_tournaments(message, t, state)
        return
    ties = await load_ties(session, competition)
    if not ties:
        league = t(f"competition-{competition}")
        await message.answer(
            f"<b>{league}</b>\n\n{t('knockout-empty')}", reply_markup=sections_menu(t)
        )
        return
    rich = rich_view.knockout_message(competition, ties, t, names, schedule.tz)
    fallback = render_knockout(competition, ties, t, names, schedule.tz)
    await answer_rich(bot, message, rich, fallback=fallback, reply_markup=sections_menu(t))


# "Orqaga": turnir ichidan ligalar ro'yxatiga, ligalar ro'yxatidan asosiy menyuga.
@router.message(TournamentsFlow.sections, MenuButton("menu-back"))
async def back_to_leagues(message: Message, t: Translator, state: FSMContext) -> None:
    await show_tournaments(message, t, state)


@router.message(TournamentsFlow.leagues, MenuButton("menu-back"))
async def back_to_main_menu(message: Message, t: Translator, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("menu-main"), reply_markup=main_menu(t))


@router.message(TournamentsFlow.sections, F.text)
async def ask_to_choose_section(message: Message, t: Translator) -> None:
    await message.answer(t("choose-hint"), reply_markup=sections_menu(t))


@router.message(TournamentsFlow.leagues, F.text)
async def ask_to_choose(message: Message, t: Translator) -> None:
    await message.answer(t("choose-hint"), reply_markup=leagues_menu(t))
