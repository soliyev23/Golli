from aiogram import Bot, F, Router
from aiogram.filters import Command, MagicData
from aiogram.types import BotCommandScopeChat, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from golli.bot.callbacks import LangCallback
from golli.bot.commands import bot_commands
from golli.bot.filters import MenuButton
from golli.bot.replies import language_prompt, welcome
from golli.db.models import User
from golli.i18n import I18n

router = Router(name="language")


# Birinchi shart til tanlamagan foydalanuvchining har qanday xabarini (jumladan /start ni) ushlaydi.
@router.message(MagicData(F.user.lang.is_(None)))
@router.message(Command("lang"))
@router.message(MenuButton("menu-language"))
async def ask_language(message: Message, i18n: I18n) -> None:
    await message.answer(**language_prompt(i18n))


@router.callback_query(LangCallback.filter())
async def set_language(
    callback: CallbackQuery,
    callback_data: LangCallback,
    user: User,
    session: AsyncSession,
    i18n: I18n,
    bot: Bot,
) -> None:
    await callback.answer()
    if callback_data.code not in i18n.locales:
        return

    user.lang = callback_data.code
    # Tanlov darhol saqlanadi: keyingi Telegram so'rovlaridan biri xato bersa ham yo'qolmaydi.
    await session.commit()

    t = i18n.translator(user.lang)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(t("lang-set"))
    await bot.send_message(user.id, **welcome(t, callback.from_user.first_name))
    # "/" menyusidagi buyruqlar tavsifi ham shu foydalanuvchi uchun tanlangan tilga o'tadi.
    await bot.set_my_commands(bot_commands(t), scope=BotCommandScopeChat(chat_id=user.id))
