from aiogram import Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated

from golli.db.models import User

router = Router(name="membership")

_BLOCKED = {ChatMemberStatus.KICKED, ChatMemberStatus.LEFT}


@router.my_chat_member()
async def on_block_or_unblock(event: ChatMemberUpdated, user: User) -> None:
    """Foydalanuvchi botni bloklasa yoki blokdan chiqarsa, Telegram shu yangilanishni yuboradi."""
    user.is_active = event.new_chat_member.status not in _BLOCKED
