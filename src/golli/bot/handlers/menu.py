from aiogram import Router
from aiogram.types import Message

from golli.bot.keyboards import main_menu
from golli.i18n import Translator

router = Router(name="menu")


# Boshqa hech bir handler ushlamagan xabar. Javob bilan birga menyu ham yangilanadi.
@router.message()
async def unknown_message(message: Message, t: Translator) -> None:
    await message.answer(t("unknown-message"), reply_markup=main_menu(t))
