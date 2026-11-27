from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from golli.bot.filters import MenuButton
from golli.bot.keyboards import main_menu, settings_menu
from golli.i18n import Translator

router = Router(name="settings")


@router.message(MenuButton("menu-settings"))
async def show_settings(message: Message, t: Translator, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("settings-text"), reply_markup=settings_menu(t))


@router.message(MenuButton("menu-back"))
async def back_to_main_menu(message: Message, t: Translator, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("menu-main"), reply_markup=main_menu(t))
