"""Bir nechta handlerda ishlatiladigan tayyor javoblar: message.answer(**javob)."""

import logging
from html import escape
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InputRichMessage, Message, ReplyKeyboardMarkup

from golli.bot.keyboards import language_picker, leagues_menu, main_menu
from golli.i18n import I18n, Translator

logger = logging.getLogger(__name__)


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
    return {"text": t("favorites-onboarding"), "reply_markup": leagues_menu(t)}


def language_prompt(i18n: I18n) -> dict[str, Any]:
    # Til hali noma'lum bo'lishi mumkin, shuning uchun savol barcha tillarda yoziladi.
    return {
        "text": "\n".join(i18n.in_all_locales("lang-choose")),
        "reply_markup": language_picker(i18n),
    }


async def answer_rich(
    bot: Bot,
    message: Message,
    rich: InputRichMessage,
    fallback: str,
    reply_markup: ReplyKeyboardMarkup | None = None,
) -> None:
    """Jadvalli (rich) xabar yuboradi; Telegram qabul qilmasa — o'sha ma'lumotni oddiy matnda."""
    try:
        await bot.send_rich_message(message.chat.id, rich, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        logger.warning("Jadvalli xabar qabul qilinmadi, oddiy matn yuborildi: %s", exc.message)
        await message.answer(fallback, reply_markup=reply_markup)
