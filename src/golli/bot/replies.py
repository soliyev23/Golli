"""Bir nechta handlerda ishlatiladigan tayyor javoblar: message.answer(**javob)."""

from html import escape
from typing import Any

from golli.bot.favorites_view import leagues_keyboard
from golli.bot.keyboards import language_picker, main_menu
from golli.i18n import I18n, Translator


def welcome(t: Translator, first_name: str, *, menu: bool = True) -> dict[str, Any]:
    """Salomlashuv. `menu=False` — ortidan boshqa klaviaturali xabar yuboriladigan holat uchun."""
    # Ism HTML sifatida yuboriladi, shuning uchun undagi < > & belgilar ekranlanadi.
    name = escape(first_name, quote=False)
    reply: dict[str, Any] = {"text": t("start-welcome", name=name)}
    if menu:
        reply["reply_markup"] = main_menu(t)
    return reply


def favorites_onboarding(t: Translator) -> dict[str, Any]:
    """Yangi foydalanuvchiga sevimli klub tanlash taklifi: ligalar klaviaturasi bilan."""
    return {"text": t("favorites-onboarding"), "reply_markup": leagues_keyboard(t)}


def language_prompt(i18n: I18n) -> dict[str, Any]:
    # Til hali noma'lum bo'lishi mumkin, shuning uchun savol barcha tillarda yoziladi.
    return {
        "text": "\n".join(i18n.in_all_locales("lang-choose")),
        "reply_markup": language_picker(i18n),
    }
