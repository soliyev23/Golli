from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from golli.db.users import get_or_create_user
from golli.i18n import I18n

Handler = Callable[[Update, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    """Har bir yangilanish uchun bitta sessiya; handler xatosiz tugasa commit qilinadi."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        async with self._session_factory() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result


class UserMiddleware(BaseMiddleware):
    """Foydalanuvchini bazadan topadi (yo'q bo'lsa yaratadi) va uning tilidagi tarjimonni beradi.

    Bot faqat shaxsiy chatda ishlaydi: guruh va kanallardan kelgan yangilanishlar
    handlerlarga yetib bormaydi.
    """

    def __init__(self, i18n: I18n) -> None:
        self._i18n = i18n

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        chat = data.get("event_chat")
        if tg_user is None or tg_user.is_bot or chat is None or chat.type != ChatType.PRIVATE:
            return None

        user = await get_or_create_user(data["session"], tg_user.id)
        if event.message is not None:
            # Xabar yozgan foydalanuvchi botni bloklamagan: avval bloklagan bo'lsa, qayta faol.
            user.is_active = True
        data["user"] = user
        data["t"] = self._i18n.translator(user.lang)
        return await handler(event, data)
