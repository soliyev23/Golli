from datetime import datetime, timedelta

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from golli.db.models import InviteLink, User

# Oxirgi faollik vaqti shundan tez-tez yozilmaydi: har bir tugma bosilishida bazaga yozuv ketmasin.
LAST_SEEN_PRECISION = timedelta(minutes=1)


async def get_or_create_user(session: AsyncSession, user_id: int) -> User:
    user, _ = await get_or_create(session, user_id)
    return user


async def get_or_create(session: AsyncSession, user_id: int) -> tuple[User, bool]:
    """Foydalanuvchi va u hozir yaratilganmi."""
    user = await session.get(User, user_id)
    if user is not None:
        return user, False
    # ON CONFLICT: bir foydalanuvchidan ikki xabar bir vaqtda kelsa ham xato bermaydi.
    result = await session.execute(
        insert(User)
        .values(id=user_id)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(User.id)
    )
    created = result.scalar() is not None
    user = await session.get(User, user_id)
    assert user is not None
    return user, created


def touch_user(user: User, tg_user: TgUser, now: datetime) -> None:
    """Telegram profilidagi ma'lumotlar va oxirgi faollik vaqtini yangilaydi."""
    user.first_name = tg_user.first_name[:128] if tg_user.first_name else None
    user.last_name = tg_user.last_name[:128] if tg_user.last_name else None
    user.username = tg_user.username
    user.language_code = tg_user.language_code
    if user.last_seen_at is None or now - user.last_seen_at >= LAST_SEEN_PRECISION:
        user.last_seen_at = now


def start_payload(text: str | None) -> str | None:
    """ "/start kod" xabaridagi kod (t.me/<bot>?start=kod havolasidan keladi)."""
    if not text or not text.startswith("/start "):
        return None
    payload = text.split(maxsplit=1)[1].strip()
    return payload[:64] or None


async def attach_invite_link(session: AsyncSession, user: User, payload: str | None) -> None:
    """Yangi foydalanuvchini u kelgan ulashish havolasiga biriktiradi."""
    if payload is None or user.invite_link_id is not None:
        return
    link_id = await session.scalar(select(InviteLink.id).where(InviteLink.code == payload))
    if link_id is not None:
        user.invite_link_id = link_id
