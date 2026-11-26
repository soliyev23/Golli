from typing import Any

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from golli.bot import favorites_view as view
from golli.bot.callbacks import FavoriteListCallback, FavoritesCallback, FavoriteToggleCallback
from golli.bot.filters import MenuButton
from golli.competitions import COMPETITIONS
from golli.db.favorites import competition_teams, favorite_teams, toggle_favorite
from golli.db.models import User
from golli.i18n import Translator
from golli.services.team_names import TeamNames

router = Router(name="favorites")


async def _root(
    session: AsyncSession, user: User, t: Translator, names: TeamNames
) -> dict[str, Any]:
    favorites = await favorite_teams(session, user.id)
    return {"text": view.root_text(favorites, t, names), "reply_markup": view.root_keyboard(t)}


async def _team_list(
    session: AsyncSession,
    user: User,
    competition: str,
    page: int,
    t: Translator,
    names: TeamNames,
) -> dict[str, Any]:
    teams = view.sort_teams(await competition_teams(session, competition), t, names)
    pages = view.page_count(teams)
    # Eski xabardagi tugma mavjud bo'lmagan sahifani ko'rsatishi mumkin.
    page = min(max(page, 0), pages - 1)
    selected = {team.id for team in await favorite_teams(session, user.id)}
    return {
        "text": view.list_text(competition, page, pages, bool(teams), t),
        "reply_markup": view.list_keyboard(competition, teams, selected, page, t, names),
    }


async def _edit(callback: CallbackQuery, content: dict[str, Any]) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(**content)
    except TelegramBadRequest as exc:
        # Matn va tugmalar o'zgarmagan bo'lsa Telegram xato qaytaradi — qiladigan ish yo'q.
        if "message is not modified" not in str(exc):
            raise


@router.message(MenuButton("menu-favorites"))
async def show_favorites(
    message: Message, user: User, session: AsyncSession, t: Translator, names: TeamNames
) -> None:
    await message.answer(**await _root(session, user, t, names))


@router.callback_query(FavoritesCallback.filter())
async def back_to_leagues(
    callback: CallbackQuery, user: User, session: AsyncSession, t: Translator, names: TeamNames
) -> None:
    await callback.answer()
    await _edit(callback, await _root(session, user, t, names))


@router.callback_query(FavoriteListCallback.filter())
async def show_teams(
    callback: CallbackQuery,
    callback_data: FavoriteListCallback,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
) -> None:
    await callback.answer()
    if callback_data.competition not in COMPETITIONS:
        return
    await _edit(
        callback,
        await _team_list(session, user, callback_data.competition, callback_data.page, t, names),
    )


@router.callback_query(FavoriteToggleCallback.filter())
async def toggle_team(
    callback: CallbackQuery,
    callback_data: FavoriteToggleCallback,
    user: User,
    session: AsyncSession,
    t: Translator,
    names: TeamNames,
) -> None:
    result = (
        await toggle_favorite(session, user.id, callback_data.team_id)
        if callback_data.competition in COMPETITIONS
        else None
    )
    if result is None:
        await callback.answer()
        return

    team, selected = result
    # Tanlov darhol saqlanadi: keyingi Telegram so'rovi xato bersa ham yo'qolmaydi.
    await session.commit()
    key = "favorites-added" if selected else "favorites-removed"
    await callback.answer(t(key, team=names.get(team.name, t.locale)))
    await _edit(
        callback,
        await _team_list(session, user, callback_data.competition, callback_data.page, t, names),
    )
