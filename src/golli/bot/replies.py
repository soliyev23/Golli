"""Bir nechta handlerda ishlatiladigan tayyor javoblar: message.answer(**javob)."""

from html import escape
from typing import Any

from golli.bot.keyboards import language_picker, main_menu
from golli.i18n import I18n, Translator


def welcome(t: Translator, first_name: str) -> dict[str, Any]:
    # Ism HTML sifatida yuboriladi, shuning uchun undagi < > & belgilar ekranlanadi.
    name = escape(first_name, quote=False)
    return {"text": t("start-welcome", name=name), "reply_markup": main_menu(t)}


def language_prompt(i18n: I18n) -> dict[str, Any]:
    # Til hali noma'lum bo'lishi mumkin, shuning uchun savol barcha tillarda yoziladi.
    return {
        "text": "\n".join(i18n.in_all_locales("lang-choose")),
        "reply_markup": language_picker(i18n),
    }
