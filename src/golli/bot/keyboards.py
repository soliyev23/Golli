from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from golli.bot.callbacks import LangCallback
from golli.i18n import I18n, Translator


def main_menu(t: Translator) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("menu-matches")),
                KeyboardButton(text=t("menu-favorites")),
            ],
            [KeyboardButton(text=t("menu-language"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def language_picker(i18n: I18n) -> InlineKeyboardMarkup:
    """Har bir til o'z nomi bilan, alohida qatorda."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.translate(locale, "lang-name"),
                    callback_data=LangCallback(code=locale).pack(),
                )
            ]
            for locale in i18n.locales
        ]
    )
