import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from golli.bot.app import create_dispatcher
from golli.bot.commands import set_bot_commands
from golli.config import Settings
from golli.db.session import create_engine, create_session_factory
from golli.i18n import I18n
from golli.services.schedule import ScheduleCache
from golli.services.team_names import TeamNames


async def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    token = settings.bot_token.get_secret_value()
    if not token:
        raise SystemExit("BOT_TOKEN berilmagan: .env fayliga @BotFather bergan tokenni yozing.")

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url)
    i18n = I18n(settings.default_locale)
    dispatcher = create_dispatcher(
        storage=RedisStorage(redis),
        session_factory=session_factory,
        i18n=i18n,
        schedule=ScheduleCache(redis, session_factory, settings.tz),
        names=TeamNames(),
    )
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    try:
        await set_bot_commands(bot, i18n)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    except TelegramUnauthorizedError:
        raise SystemExit("BOT_TOKEN noto'g'ri: Telegram uni qabul qilmadi.") from None
    finally:
        await bot.session.close()
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
