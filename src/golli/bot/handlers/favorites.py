from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from golli.bot import favorites_view as view
from golli.bot.callbacks import FavoriteListCallback, FavoritesCallback, FavoriteToggleCallback
from golli.bot.filters import LeagueButton, MenuButton
from golli.bot.keyboards import leagues_menu, settings_menu
from golli.bot.replies import welcome
from golli.bot.states import FROM_SETTINGS, FROM_START, FavoritesFlow, open_favorites
from golli.bot.views import club_label
from golli.competitions import COMPETITIONS
from golli.db.favorites import competition_teams, favorite_teams, toggle_favorite
from golli.db.models import User
from golli.i18n import Translator
from golli.services.team_names import TeamNames

router = Router(name="favorites")


async def _onboarding(state: FSMContext) -> bool:
    """Birinchi tanishuvdagi klub tanlashmi? Unda klaviaturalarda "Tayyor" tugmasi bo'ladi."""
    return (await state.get_data()).get("origin") == FROM_START


async def _leagues(
    session: AsyncSession, user: User, t: Translator, names: TeamNames, state: FSMContext
) -> dict[str, Any]:
    favorites = await favorite_teams(session, user.id)
    return {
        "text": view.root_text(favorites, t, names),
        "reply_markup": leagues_menu(t, done=await _onboarding(state)),
    }


async def _clubs(
    session: AsyncSession,
    user: User,
    competition: str,
    t: Translator,
    names: TeamNames,
    state: FSMContext,
    text: str | None = None,
) -> dict[str, Any]:
    """Liga klublari klaviaturasi; `text` berilmasa, liga nomi va yo'riqnoma yoziladi."""
    teams = view.sort_teams(await competition_teams(session, competition), t, names)
    selected = {team.id for team in await favorite_teams(session, user.id)}
    done = await _onboarding(state)
    return {
        "text": text or view.clubs_text(competition, bool(teams), t),
        "reply_markup": view.clubs_keyboard(teams, selected, t, names, done=done),
    }


@router.message(MenuButton("menu-favorites"))
async def show_leagues(
    message: Message,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    state: FSMContext,
) -> None:
    await open_favorites(state, FROM_SETTINGS)
    await message.answer(**await _leagues(session, user, t, names, state))


# Liga tugmalari "Turnirlar" bo'limida ham bor, shuning uchun bu yerda faqat shu bo'lim
# ichida (holatga qarab) ushlanadi.
@router.message(StateFilter(FavoritesFlow), LeagueButton())
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
    await message.answer(**await _clubs(session, user, competition, t, names, state))


# "Orqaga" har bosqichda bir qadam ortga qaytaradi: klublardan ligalarga, ligalardan esa
# bo'limga kirilgan joyga.
@router.message(FavoritesFlow.clubs, MenuButton("menu-back"))
async def back_to_leagues(
    message: Message,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    state: FSMContext,
) -> None:
    await state.set_state(FavoritesFlow.leagues)
    await message.answer(**await _leagues(session, user, t, names, state))


# "Tayyor" — birinchi tanishuvdagi klub tanlashni yakunlaydi: shundan keyin salomlashuv va
# asosiy menyu chiqadi. Ligalar ro'yxatidagi "Orqaga" ham bo'limdan chiqaradi: Sozlamalardan
# kirilgan bo'lsa — Sozlamalarga.
@router.message(StateFilter(FavoritesFlow), MenuButton("favorites-done"))
@router.message(FavoritesFlow.leagues, MenuButton("menu-back"))
async def leave(message: Message, t: Translator, state: FSMContext) -> None:
    onboarding = await _onboarding(state)
    await state.clear()
    if onboarding:
        await message.answer(**welcome(t, message.from_user.first_name))
    else:
        await message.answer(t("settings-text"), reply_markup=settings_menu(t))


# Bo'lim ichidagi boshqa har qanday matn: klublar ro'yxatida — klub tugmasi.
@router.message(StateFilter(FavoritesFlow), F.text)
async def toggle_club(
    message: Message,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
    state: FSMContext,
) -> None:
    competition = (await state.get_data()).get("competition")
    in_club_list = await state.get_state() == FavoritesFlow.clubs.state
    if not in_club_list or competition not in COMPETITIONS:
        await state.set_state(FavoritesFlow.leagues)
        markup = leagues_menu(t, done=await _onboarding(state))
        await message.answer(t("choose-hint"), reply_markup=markup)
        return

    teams = view.sort_teams(await competition_teams(session, competition), t, names)
    team = view.find_club(message.text, teams, t, names)
    if team is None:
        hint = t("choose-hint")
        await message.answer(**await _clubs(session, user, competition, t, names, state, text=hint))
        return

    _, selected = await toggle_favorite(session, user.id, team.id)
    # Tanlov darhol saqlanadi: keyingi Telegram so'rovi xato bersa ham yo'qolmaydi.
    await session.commit()
    result = t(
        "favorites-added" if selected else "favorites-removed",
        team=club_label(team.name, team.emoji_id, t, names),
    )
    # Tugmadagi ✅ belgisi yangilanishi uchun klaviatura qayta yuboriladi.
    await message.answer(**await _clubs(session, user, competition, t, names, state, text=result))


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
