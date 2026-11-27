from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from golli.bot import favorites_view as view
from golli.bot.callbacks import FavoriteListCallback, FavoritesCallback, FavoriteToggleCallback
from golli.bot.filters import LeagueButton, MenuButton
from golli.bot.keyboards import main_menu
from golli.bot.views import club_label
from golli.competitions import COMPETITIONS
from golli.db.favorites import competition_teams, favorite_teams, toggle_favorite
from golli.db.models import User
from golli.i18n import Translator
from golli.services.team_names import TeamNames

router = Router(name="favorites")


class FavoritesFlow(StatesGroup):
    # Foydalanuvchi bitta liganing klublari ro'yxatida turibdi: bosgan tugmasining matni
    # klub nomi deb o'qiladi. Qaysi liga ekani holat ma'lumotida ("competition") saqlanadi.
    clubs = State()


async def _leagues(
    session: AsyncSession, user: User, t: Translator, names: TeamNames
) -> dict[str, Any]:
    favorites = await favorite_teams(session, user.id)
    return {"text": view.root_text(favorites, t, names), "reply_markup": view.leagues_keyboard(t)}


async def _clubs(
    session: AsyncSession,
    user: User,
    competition: str,
    t: Translator,
    names: TeamNames,
    text: str | None = None,
) -> dict[str, Any]:
    """Liga klublari klaviaturasi; `text` berilmasa, liga nomi va yo'riqnoma yoziladi."""
    teams = view.sort_teams(await competition_teams(session, competition), t, names)
    selected = {team.id for team in await favorite_teams(session, user.id)}
    return {
        "text": text or view.clubs_text(competition, bool(teams), t),
        "reply_markup": view.clubs_keyboard(teams, selected, t, names),
    }


@router.message(MenuButton("menu-favorites"))
@router.message(MenuButton("favorites-back"))
async def show_leagues(
    message: Message,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(**await _leagues(session, user, t, names))


@router.message(LeagueButton())
async def show_clubs(
    message: Message,
    competition: str,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    state: FSMContext,
) -> None:
    await state.set_state(FavoritesFlow.clubs)
    await state.update_data(competition=competition)
    await message.answer(**await _clubs(session, user, competition, t, names))


@router.message(MenuButton("favorites-done"))
async def finish(
    message: Message,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    state: FSMContext,
) -> None:
    await state.clear()
    favorites = await favorite_teams(session, user.id)
    await message.answer(view.summary_text(favorites, t, names), reply_markup=main_menu(t))


# Klublar ro'yxatida turgan foydalanuvchining boshqa har qanday matni — klub tugmasi.
@router.message(FavoritesFlow.clubs, F.text)
async def toggle_club(
    message: Message,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    state: FSMContext,
) -> None:
    competition = (await state.get_data()).get("competition")
    if competition not in COMPETITIONS:
        await state.clear()
        await message.answer(**await _leagues(session, user, t, names))
        return

    teams = view.sort_teams(await competition_teams(session, competition), t, names)
    team = view.find_club(message.text, teams, t, names)
    if team is None:
        hint = t("favorites-choose-hint")
        await message.answer(**await _clubs(session, user, competition, t, names, text=hint))
        return

    _, selected = await toggle_favorite(session, user.id, team.id)
    # Tanlov darhol saqlanadi: keyingi Telegram so'rovi xato bersa ham yo'qolmaydi.
    await session.commit()
    result = t(
        "favorites-added" if selected else "favorites-removed",
        team=club_label(team.name, team.emoji_id, t, names),
    )
    # Tugmadagi ✅ belgisi yangilanishi uchun klaviatura qayta yuboriladi.
    await message.answer(**await _clubs(session, user, competition, t, names, text=result))


# Avval bu bo'lim xabar ostidagi (inline) tugmalar bilan ishlagan. Eski xabarda qolgan
# shunday tugma bosilsa, foydalanuvchi pastki menyuga yo'naltiriladi va tugmalar olinadi.
@router.callback_query(FavoritesCallback.filter())
@router.callback_query(FavoriteListCallback.filter())
@router.callback_query(FavoriteToggleCallback.filter())
async def retire_old_buttons(callback: CallbackQuery, t: Translator) -> None:
    await callback.answer(t("buttons-outdated"))
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
