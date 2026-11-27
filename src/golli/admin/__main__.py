"""Admin panelni ishga tushirish: python -m golli.admin

Konteyner ichida 0.0.0.0:8000 da tinglaydi; tashqariga docker-compose 127.0.0.1:8095 orqali
chiqaradi, internetga esa Caddy (HTTPS) ulaydi.
"""

import logging

import uvicorn
from aiogram import Bot

from golli.admin.app import create_app
from golli.config import Settings
from golli.db.session import create_engine, create_session_factory


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if (
        not settings.admin_password_hash.get_secret_value()
        or not settings.admin_secret.get_secret_value()
    ):
        raise SystemExit(
            "ADMIN_PASSWORD_HASH va ADMIN_SECRET .env faylida berilishi kerak "
            "(xesh: python -m golli.admin.hash_password)."
        )
    session_factory = create_session_factory(create_engine(settings))

    async def bot_username() -> str:
        if settings.bot_username:
            return settings.bot_username
        bot = Bot(settings.bot_token.get_secret_value())
        try:
            return (await bot.me()).username
        finally:
            await bot.session.close()

    app = create_app(settings, session_factory, bot_username)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        # Port faqat 127.0.0.1 ga chiqarilgan: so'rov faqat serverdagi Caddy'dan keladi.
        forwarded_allow_ips="*",
        log_level=settings.log_level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
