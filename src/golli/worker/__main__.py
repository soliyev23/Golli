"""Fon jarayoni: futbol ma'lumotlarini provayderdan olib, bazaga va keshga yozadi,
eslatmalarni rejalaydi va yuboradi.

Bitta nusxada ishlaydi (docker-compose'dagi "worker" servisi).
"""

import asyncio
import contextlib
import logging
import signal
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from redis.asyncio import Redis

from golli.config import Settings
from golli.db.session import create_engine, create_session_factory
from golli.i18n import I18n
from golli.providers.highlightly import HighlightlyProvider
from golli.services.club_emoji import ClubEmojiSyncer
from golli.services.reminders import ReminderPlanner, Sender
from golli.services.schedule import ScheduleCache
from golli.services.sync import Syncer
from golli.services.team_names import TeamNames

TICK_SECONDS = 60

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx har bir so'rovni INFO darajasida to'liq manzili bilan yozadi — ortiqcha.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    api_key = settings.highlightly_api_key.get_secret_value()
    if not api_key:
        raise SystemExit("HIGHLIGHTLY_API_KEY berilmagan: .env fayliga API kalitini yozing.")
    token = settings.bot_token.get_secret_value()
    if not token:
        raise SystemExit("BOT_TOKEN berilmagan: .env fayliga @BotFather bergan tokenni yozing.")

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url)
    provider = HighlightlyProvider(api_key)
    # Faqat xabar yuborish uchun; yangilanishlarni bot jarayoni qabul qiladi.
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    schedule = ScheduleCache(redis, session_factory, settings.tz)
    syncer = Syncer(
        provider=provider,
        session_factory=session_factory,
        schedule=schedule,
        redis=redis,
        tz=settings.tz,
    )
    club_emoji = ClubEmojiSyncer(bot, session_factory, schedule, settings.emoji_owner_id)
    planner = ReminderPlanner(session_factory, redis, settings.tz)
    sender = Sender(bot, session_factory, I18n(settings.default_locale), TeamNames(), settings.tz)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)

    logger.info("Worker ishga tushdi (provayder: %s)", provider.name)
    sending = asyncio.create_task(sender.run(stop))
    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            # Avval ma'lumot yangilanadi, keyin shu ma'lumot bo'yicha eslatmalar rejalanadi.
            await syncer.tick(now)
            try:
                await club_emoji.tick(now)
            except Exception:
                logger.exception("Klub emojilari: kutilmagan xato")
            try:
                await planner.plan(now)
            except Exception:
                logger.exception("Eslatmalarni rejalash: kutilmagan xato")
            # Keyingi aylanishgacha kutadi; to'xtatish signali kelsa darhol chiqadi.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
    finally:
        stop.set()
        await sending
        await club_emoji.aclose()
        await bot.session.close()
        await provider.aclose()
        await redis.aclose()
        await engine.dispose()
        logger.info("Worker to'xtadi")


if __name__ == "__main__":
    asyncio.run(main())
