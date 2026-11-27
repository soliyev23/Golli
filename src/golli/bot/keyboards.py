from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from golli.bot.callbacks import LangCallback
from golli.competitions import COMPETITIONS
from golli.i18n import I18n, Translator

# Pastki klaviaturalarda is_persistent qo'yilmaydi: u bilan Telegram klaviaturani doim ochiq
# ushlab turadi va yozish maydonidagi "klaviaturani yashirish" tugmasini ko'rsatmaydi.


def main_menu(t: Translator) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("menu-matches")),
                KeyboardButton(text=t("menu-recent")),
            ],
            [
                KeyboardButton(text=t("menu-tournaments")),
                KeyboardButton(text=t("menu-settings")),
            ],
        ],
        resize_keyboard=True,
    )


def sections_menu(t: Translator) -> ReplyKeyboardMarkup:
    """Pley-off bosqichi bor turnir tanlanganda: jadval yoki pley-off juftliklari."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("menu-table")),
                KeyboardButton(text=t("menu-knockout")),
            ],
            [KeyboardButton(text=t("menu-back"))],
        ],
        resize_keyboard=True,
    )


def leagues_menu(t: Translator, *, done: bool = False) -> ReplyKeyboardMarkup:
    """Ligalar ro'yxati va "Orqaga". Sevimli klublar va turnirlar bo'limlarida ishlatiladi.

    `done` — birinchi tanishuvdagi klub tanlash: "Orqaga" o'rnida "Tayyor" turadi.
    """
    first, *others = [KeyboardButton(text=t(f"competition-{code}")) for code in COMPETITIONS]
    last = KeyboardButton(text=t("favorites-done" if done else "menu-back"))
    return ReplyKeyboardMarkup(
        # Birinchi liga nomi uzun ("Chempionlar ligasi"), shuning uchun u alohida qatorda.
        keyboard=[[first], others, [last]],
        resize_keyboard=True,
    )


def settings_menu(t: Translator) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("menu-favorites")),
                KeyboardButton(text=t("menu-language")),
            ],
            [KeyboardButton(text=t("menu-back"))],
        ],
        resize_keyboard=True,
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
