"""Klub logotiplari — Telegram'ning maxsus emojisi sifatida.

Matnli xabar ichida rasm ko'rsatishning yagona yo'li — maxsus emoji. Worker har bir klub
logotipini provayder bergan havoladan olib, 100x100 PNG ga keltiradi, botning emoji
to'plamiga qo'shadi va emoji identifikatorini teams.emoji_id ga yozadi. Xabarlarda u
<tg-emoji> tegi bilan klub nomi oldiga qo'yiladi (bot/views.py).

Bot maxsus emojini faqat egasida Telegram Premium bo'lsa (yoki botga Fragment'dan
qo'shimcha username olingan bo'lsa) ishlata oladi. Aks holda Telegram uning o'rnida
FALLBACK_EMOJI ni ko'rsatadi.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from io import BytesIO

import httpx
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.types import BufferedInputFile, InputSticker
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from golli.db.models import Team
from golli.services.schedule import ScheduleCache

logger = logging.getLogger(__name__)

# Maxsus emoji ko'rsatib bo'lmaydigan joyda (masalan, tizim bildirishnomasida) shu chiqadi.
FALLBACK_EMOJI = "⚽"
# Telegram talabi: statik maxsus emoji aynan 100x100 piksel, PNG yoki WEBP.
EMOJI_SIZE = 100
# Telegram cheklovi: bitta emoji to'plamida ko'pi bilan 200 ta.
SET_LIMIT = 200
SET_TITLE = "Golli · klublar"
# Bitta aylanishda yaratiladigan emojilar: aylanish cho'zilib, boshqa vazifalarni kuttirmasin.
BATCH = 20
# Telegram xatosidan keyin (tarmoq, vaqtinchalik nosozlik) shuncha vaqt kutiladi.
RETRY_DELAY = timedelta(minutes=30)
# Logotipini olib yoki o'qib bo'lmagan klubga shuncha vaqtdan keyin qayta uriniladi.
BROKEN_LOGO_DELAY = timedelta(hours=6)

FetchLogo = Callable[[str], Awaitable[bytes]]


class EmojiSetError(Exception):
    """To'plam kutilgan holatda emas (masalan, qo'shilgan emoji unda ko'rinmadi)."""


def to_emoji_png(data: bytes) -> bytes:
    """Istalgan rasmni shaffof fonli 100x100 PNG ga keltiradi, nisbatini buzmasdan."""
    with Image.open(BytesIO(data)) as source:
        logo = ImageOps.contain(source.convert("RGBA"), (EMOJI_SIZE, EMOJI_SIZE), Image.LANCZOS)
    canvas = Image.new("RGBA", (EMOJI_SIZE, EMOJI_SIZE), (0, 0, 0, 0))
    canvas.paste(logo, ((EMOJI_SIZE - logo.width) // 2, (EMOJI_SIZE - logo.height) // 2))
    output = BytesIO()
    canvas.save(output, "PNG", optimize=True)
    return output.getvalue()


class ClubEmojiSyncer:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        schedule: ScheduleCache,
        owner_id: int | None,
        fetch_logo: FetchLogo | None = None,
    ) -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._schedule = schedule
        self._owner_id = owner_id
        self._client: httpx.AsyncClient | None = None
        self._fetch_logo = fetch_logo or self._download
        self._retry_after: datetime | None = None
        self._broken_until: dict[int, datetime] = {}
        # Hozir to'ldirilayotgan to'plam: tartib raqami, nomi, Telegram'da bor-yo'qligi va
        # undagi emojilar. _set_emoji None bo'lsa, holat noma'lum — Telegram'dan qayta o'qiladi.
        self._set_index = 1
        self._set_name: str | None = None
        self._set_exists = False
        self._set_emoji: set[str] | None = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def tick(self, now: datetime) -> None:
        """Emojisi yo'q klublarga emoji yaratadi. Ish bo'lmasa Telegram'ga murojaat qilmaydi."""
        if self._owner_id is None or (self._retry_after is not None and now < self._retry_after):
            return
        teams = await self._teams_without_emoji(now)
        if not teams:
            return

        created = 0
        try:
            for team in teams:
                try:
                    image = to_emoji_png(await self._fetch_logo(team.logo_url))
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    # Bitta klubning buzuq logotipi qolganlarini to'xtatmaydi.
                    self._broken_until[team.id] = now + BROKEN_LOGO_DELAY
                    logger.warning("Logotip olinmadi (%s): %s", team.name, exc)
                    continue
                emoji_id = await self._add_emoji(team.name, image)
                async with self._session_factory.begin() as session:
                    stored = await session.get(Team, team.id)
                    stored.emoji_id = emoji_id
                created += 1
        except TelegramRetryAfter as exc:
            self._pause(now, timedelta(seconds=exc.retry_after))
            logger.warning("Emoji yaratish: Telegram %s soniya kutishni so'radi", exc.retry_after)
        except (TelegramAPIError, EmojiSetError) as exc:
            self._pause(now, RETRY_DELAY)
            logger.warning("Emoji yaratish: %s", exc)
        finally:
            if created:
                # Ro'yxatlar keshdan o'qiladi: yangi emojilar ko'rinishi uchun kesh qayta quriladi.
                await self._schedule.rebuild(now)
                logger.info("Klub emojilari: %s ta yaratildi", created)

    def _pause(self, now: datetime, delay: timedelta) -> None:
        self._retry_after = now + delay
        # Xatodan keyin to'plam holati noaniq: keyingi safar Telegram'dan qayta o'qiladi.
        self._set_emoji = None

    async def _teams_without_emoji(self, now: datetime) -> list[Team]:
        broken = [team_id for team_id, until in self._broken_until.items() if until > now]
        query = (
            select(Team)
            .where(Team.emoji_id.is_(None), Team.logo_url.is_not(None))
            .order_by(Team.id)
            .limit(BATCH)
        )
        if broken:
            query = query.where(Team.id.not_in(broken))
        async with self._session_factory() as session:
            return list(await session.scalars(query))

    async def _add_emoji(self, label: str, image: bytes) -> str:
        """Rasmni to'plamga qo'shib, emoji identifikatorini qaytaradi.

        `label` — xato matnida ko'rsatiladigan nom.
        """
        if self._set_emoji is None:
            await self._open_set()
        sticker = InputSticker(
            sticker=BufferedInputFile(image, filename="emoji.png"),
            format="static",
            emoji_list=[FALLBACK_EMOJI],
        )
        if self._set_exists:
            await self._bot.add_sticker_to_set(
                user_id=self._owner_id, name=self._set_name, sticker=sticker
            )
        else:
            # To'plam birinchi emojisi bilan birga yaratiladi.
            await self._bot.create_new_sticker_set(
                user_id=self._owner_id,
                name=self._set_name,
                title=SET_TITLE,
                stickers=[sticker],
                sticker_type="custom_emoji",
            )
        before = self._set_emoji
        self._set_emoji = None
        after = await self._read_set(self._set_name)
        added = (after or set()) - before
        if len(added) != 1:
            raise EmojiSetError(f"{label}: to'plamda {len(added)} ta yangi emoji (1 kutilgan)")
        self._set_exists, self._set_emoji = True, after
        if len(after) >= SET_LIMIT:
            # To'plam to'ldi: keyingi emoji yangi to'plamga tushadi.
            self._set_index += 1
            self._set_emoji = None
        return added.pop()

    async def _open_set(self) -> None:
        """Bo'sh joyi bor to'plamni topadi va undagi egasiz emojilarni olib tashlaydi."""
        username = (await self._bot.me()).username
        async with self._session_factory() as session:
            in_use = set(
                await session.scalars(select(Team.emoji_id).where(Team.emoji_id.is_not(None)))
            )
        while True:
            name = f"clubs{self._set_index}_by_{username}"
            stickers = await self._read_set(name, with_files=True)
            if stickers is None:
                self._set_name, self._set_exists, self._set_emoji = name, False, set()
                return
            # Bazada yo'q emoji — yarim yo'lda uzilgan urinish qoldig'i (yoki baza tozalangan).
            # Qolib ketsa joy egallaydi va aynan shu rasmni qayta qo'shishga xalaqit beradi.
            orphans = [file_id for emoji_id, file_id in stickers.items() if emoji_id not in in_use]
            for file_id in orphans:
                await self._bot.delete_sticker_from_set(sticker=file_id)
            # Oxirgi emojisi o'chirilgan to'plam Telegram'da qolmasligi mumkin: qayta o'qiladi.
            kept = await self._read_set(name) if orphans else set(stickers)
            if kept is None or len(kept) < SET_LIMIT:
                self._set_name, self._set_exists = name, kept is not None
                self._set_emoji = kept or set()
                return
            self._set_index += 1

    async def _read_set(self, name: str, with_files: bool = False):
        """To'plamdagi emojilar: identifikatorlar to'plami yoki {identifikator: file_id}.

        To'plam hali yaratilmagan bo'lsa — None.
        """
        try:
            sticker_set = await self._bot.get_sticker_set(name)
        except TelegramBadRequest as exc:
            if "STICKERSET_INVALID" in exc.message:
                return None
            raise
        files = {sticker.custom_emoji_id: sticker.file_id for sticker in sticker_set.stickers}
        return files if with_files else set(files)

    async def _download(self, url: str) -> bytes:
        if not url.startswith("https://"):
            raise ValueError(f"kutilmagan havola: {url!r}")
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20, follow_redirects=True)
        response = await self._client.get(url)
        response.raise_for_status()
        return response.content
