from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from golli.bot.keyboards import main_menu
from golli.bot.replies import welcome
from golli.i18n import Translator

router = Router(name="start")


# Til tanlamagan foydalanuvchi bu yerga yetib kelmaydi — uni language routeri ushlaydi.
@router.message(CommandStart())
async def cmd_start(message: Message, t: Translator) -> None:
    await message.answer(**welcome(t, message.from_user.first_name))


@router.message(Command("help"))
async def cmd_help(message: Message, t: Translator) -> None:
    await message.answer(t("help-text"), reply_markup=main_menu(t))
