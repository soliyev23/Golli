import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from html import escape
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Update
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from golli.db.models import InviteLink, User
from golli.db.users import attach_invite_link, get_or_create, start_payload, touch_user
from golli.i18n import I18n

logger = logging.getLogger(__name__)

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

    def __init__(self, i18n: I18n, new_user_alert_chat_id: int | None = None) -> None:
        self._i18n = i18n
        self._alert_chat_id = new_user_alert_chat_id

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        chat = data.get("event_chat")
        if tg_user is None or tg_user.is_bot or chat is None or chat.type != ChatType.PRIVATE:
            return None

        session = data["session"]
        user, created = await get_or_create(session, tg_user.id)
        touch_user(user, tg_user, datetime.now(UTC))
        if created and event.message is not None:
            # Birinchi kirish: ulashish havolasi orqali kelgan bo'lsa, manbasi yozib qo'yiladi.
            await attach_invite_link(session, user, start_payload(event.message.text))
        if event.message is not None:
            # Xabar yozgan foydalanuvchi botni bloklamagan: avval bloklagan bo'lsa, qayta faol.
            user.is_active = True
        data["user"] = user
        data["t"] = self._i18n.translator(user.lang)
        result = await handler(event, data)
        if created and self._alert_chat_id is not None and self._alert_chat_id != user.id:
            link = (
                await session.get(InviteLink, user.invite_link_id) if user.invite_link_id else None
            )
            await self._alert(data["bot"], new_user_alert(tg_user, user, link))
        return result

    async def _alert(self, bot: Bot, text: str) -> None:
        # Xabar yetmasa ham foydalanuvchiga javob buzilmasin: xato faqat logga yoziladi.
        try:
            await bot.send_message(self._alert_chat_id, text, parse_mode=ParseMode.HTML)
        except TelegramAPIError as exc:
            logger.warning("Yangi foydalanuvchi haqida xabar yuborilmadi: %s", exc)


def new_user_alert(tg_user: TgUser, user: User, link: InviteLink | None) -> str:
    """Bot egasiga boradigan xabar: yangi foydalanuvchining ismi, username'i va qayerdan kelgani."""
    lines = ["🆕 <b>Yangi foydalanuvchi</b>", escape(tg_user.full_name)]
    if tg_user.username:
        lines.append(f"@{escape(tg_user.username)}")
    lines.append(f"ID: <code>{user.id}</code>")
    if link is not None:
        lines.append(f"Havola: {escape(link.name)}")
    return "\n".join(lines)
