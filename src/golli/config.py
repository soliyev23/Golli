from zoneinfo import ZoneInfo

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Barcha sozlamalar muhit o'zgaruvchilari yoki .env faylidan o'qiladi."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Bo'sh bo'lishi mumkin: migratsiya va testlarga token kerak emas, bot esa
    # ishga tushishda tokenni o'zi tekshiradi. API kaliti ham shunday: u faqat worker'ga kerak.
    bot_token: SecretStr = SecretStr("")
    highlightly_api_key: SecretStr = SecretStr("")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "golli"
    postgres_user: str = "golli"
    postgres_password: SecretStr = SecretStr("")

    redis_url: str = "redis://localhost:6379/0"

    # Veb admin panel. Parol ochiq holda saqlanmaydi, faqat xeshi:
    # python -m golli.admin.hash_password. ADMIN_SECRET — sessiya cookie'sini imzolash kaliti.
    admin_username: str = "admin"
    admin_password_hash: SecretStr = SecretStr("")
    admin_secret: SecretStr = SecretStr("")
    # Ulashish havolalari uchun bot username'i; bo'sh bo'lsa, Telegram'dan so'raladi.
    bot_username: str = ""

    # Klub logotiplari emoji to'plamining egasi bo'ladigan Telegram foydalanuvchisi (ID).
    # Berilmagan bo'lsa, emoji yaratilmaydi va klublar logotipsiz ko'rsatiladi.
    emoji_owner_id: int | None = None

    default_locale: str = "uz"
    # O'yin vaqtlari va "bugun" tushunchasi shu vaqt mintaqasida hisoblanadi.
    timezone: str = "Asia/Tashkent"
    log_level: str = "INFO"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value() or None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
