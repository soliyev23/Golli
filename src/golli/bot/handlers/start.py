from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from golli.bot.keyboards import main_menu
from golli.bot.replies import favorites_onboarding, welcome
from golli.db.favorites import favorite_teams
from golli.db.models import User
from golli.i18n import Translator

router = Router(name="start")


# Til tanlamagan foydalanuvchi bu yerga yetib kelmaydi — uni language routeri ushlaydi.
@router.message(CommandStart())
async def cmd_start(
    message: Message, user: User, session: AsyncSession, t: Translator, state: FSMContext
) -> None:
    await state.clear()
    first_name = message.from_user.first_name
    if await favorite_teams(session, user.id):
        await message.answer(**welcome(t, first_name))
        return
    # Sevimli klubi yo'q foydalanuvchi: salomlashuvdan keyin darhol klub tanlash taklif qilinadi.
    await message.answer(**welcome(t, first_name, menu=False))
    await message.answer(**favorites_onboarding(t))


@router.message(Command("help"))
async def cmd_help(message: Message, t: Translator, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("help-text"), reply_markup=main_menu(t))
