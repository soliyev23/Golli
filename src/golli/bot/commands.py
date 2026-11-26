from aiogram import Bot
from aiogram.types import BotCommand

from golli.i18n import I18n, Translator


def bot_commands(t: Translator) -> list[BotCommand]:
    return [
        BotCommand(command="start", description=t("cmd-start")),
        BotCommand(command="lang", description=t("cmd-lang")),
        BotCommand(command="help", description=t("cmd-help")),
    ]


async def set_bot_commands(bot: Bot, i18n: I18n) -> None:
    """Til tanlamagan foydalanuvchilar uchun: buyruqlar Telegram ilovasi tilida ko'rinadi."""
    for locale in i18n.locales:
        # Asosiy til barcha foydalanuvchilarga, qolganlari faqat o'sha tildagilarga ko'rinadi.
        language_code = None if locale == i18n.default_locale else locale
        await bot.set_my_commands(
            bot_commands(i18n.translator(locale)), language_code=language_code
        )
