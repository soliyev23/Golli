"""Testlar uchun umumiy tayyorgarlik.

Baza testlari haqiqiy PostgreSQL'da, alohida "<POSTGRES_DB>_test" bazasida ishlaydi
(asosiy bazaga tegilmaydi). Bazaga ulanib bo'lmasa, o'sha testlar o'tkazib yuboriladi.
Telegram'ga so'rov ketmaydi: bot yubormoqchi bo'lgan xabarlar RecordingSession'da yig'iladi.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AddStickerToSet,
    CreateNewStickerSet,
    DeleteStickerFromSet,
    GetMe,
    GetStickerSet,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberBanned,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    Sticker,
    StickerSet,
    Update,
)
from aiogram.types import User as TgUser
from alembic import command
from alembic.config import Config
from fakeredis import FakeAsyncRedis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from factories import BOT_USERNAME
from golli.bot.app import create_dispatcher
from golli.config import Settings
from golli.i18n import I18n
from golli.services.schedule import ScheduleCache
from golli.services.team_names import TeamNames

ROOT = Path(__file__).parent.parent
BOT_ID = 123456


class RecordingSession(BaseSession):
    """Telegram o'rniga: so'rovlarni tarmoqqa chiqarmay, ro'yxatga yozib boradi."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        # chat_id -> xato yasovchi: shu chatga xabar yuborish Telegram xatosi bilan tugaydi.
        self.failures: dict[int, Callable[[TelegramMethod], Exception]] = {}
        # So'rov turi -> xato yasovchi: shu turdagi har bir so'rov xato bilan tugaydi.
        self.method_failures: dict[type, Callable[[TelegramMethod], Exception]] = {}
        # Botning emoji to'plamlari: nom -> emojilar. Telegram kabi identifikator beradi.
        self.sticker_sets: dict[str, list[Sticker]] = {}
        self._stickers_made = 0

    async def close(self) -> None:
        pass

    def add_sticker(self, set_name: str) -> Sticker:
        """To'plamga yangi maxsus emoji qo'shadi (to'plam bo'lmasa, yaratadi)."""
        self._stickers_made += 1
        number = self._stickers_made
        sticker = Sticker(
            file_id=f"file-{number}",
            file_unique_id=f"unique-{number}",
            type="custom_emoji",
            width=100,
            height=100,
            is_animated=False,
            is_video=False,
            set_name=set_name,
            custom_emoji_id=str(5000 + number),
        )
        self.sticker_sets.setdefault(set_name, []).append(sticker)
        return sticker

    def _sticker_request(self, method):
        if isinstance(method, CreateNewStickerSet):
            if method.name in self.sticker_sets:
                raise TelegramBadRequest(method=method, message="Bad Request: name is occupied")
            for _ in method.stickers:
                self.add_sticker(method.name)
            return True
        if isinstance(method, AddStickerToSet):
            self.add_sticker(method.name)
            return True
        if isinstance(method, GetStickerSet):
            if method.name not in self.sticker_sets:
                raise TelegramBadRequest(method=method, message="Bad Request: STICKERSET_INVALID")
            return StickerSet(
                name=method.name,
                title="test",
                sticker_type="custom_emoji",
                stickers=list(self.sticker_sets[method.name]),
            )
        # DeleteStickerFromSet. Haqiqiy Telegram'dagidek: oxirgi emojisi o'chirilgan to'plam
        # yo'qolmaydi, bo'sh holda qoladi.
        for name, stickers in self.sticker_sets.items():
            self.sticker_sets[name] = [s for s in stickers if s.file_id != method.sticker]
        return True

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if type(method) in self.method_failures:
            raise self.method_failures[type(method)](method)
        if isinstance(method, SendMessage) and method.chat_id in self.failures:
            raise self.failures[method.chat_id](method)
        if isinstance(method, GetMe):
            return TgUser(id=BOT_ID, is_bot=True, first_name="Golli", username=BOT_USERNAME)
        if isinstance(
            method, CreateNewStickerSet | AddStickerToSet | GetStickerSet | DeleteStickerFromSet
        ):
            return self._sticker_request(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=len(self.requests),
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""


class PrivateChat:
    """Bitta foydalanuvchining bot bilan shaxsiy chatini taqlid qiladi."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        bot: Bot,
        user_id: int = 1001,
        first_name: str = "Ali",
        language_code: str | None = "uz",
        chat_type: str = "private",
    ) -> None:
        self._dispatcher = dispatcher
        self._bot = bot
        self._update_id = 0
        self.user_id = user_id
        self.tg_user = TgUser(
            id=user_id, is_bot=False, first_name=first_name, language_code=language_code
        )
        self.chat = Chat(id=user_id, type=chat_type)
        # Botning oxirgi yangilanishga javoban yuborgan barcha so'rovlari, tartibi bilan.
        self.requests: list[TelegramMethod] = []

    async def _feed(self, **event) -> list[SendMessage]:
        session: RecordingSession = self._bot.session
        before = len(session.requests)
        self._update_id += 1
        await self._dispatcher.feed_update(self._bot, Update(update_id=self._update_id, **event))
        self.requests = session.requests[before:]
        return [m for m in self.requests if isinstance(m, SendMessage)]

    async def press(self, callback_data: str) -> list[SendMessage]:
        """Foydalanuvchi bot xabari ostidagi inline tugmani bosadi."""
        bot_user = TgUser(id=BOT_ID, is_bot=True, first_name="Golli")
        query = CallbackQuery(
            id=str(self._update_id + 1),
            from_user=self.tg_user,
            chat_instance="test",
            data=callback_data,
            message=Message(
                message_id=self._update_id,
                date=datetime.now(UTC),
                chat=self.chat,
                from_user=bot_user,
                text="tugmali xabar",
            ),
        )
        return await self._feed(callback_query=query)

    async def choose_language(self, code: str) -> list[SendMessage]:
        return await self.press(f"lang:{code}")

    async def send(self, text: str) -> list[SendMessage]:
        """Foydalanuvchi xabar yozadi; botning javob xabarlari qaytadi."""
        message = Message(
            message_id=self._update_id + 1,
            date=datetime.now(UTC),
            chat=self.chat,
            from_user=self.tg_user,
            text=text,
        )
        return await self._feed(message=message)

    async def block(self) -> list[SendMessage]:
        """Foydalanuvchi botni bloklaydi."""
        bot_user = TgUser(id=BOT_ID, is_bot=True, first_name="Golli")
        event = ChatMemberUpdated(
            chat=self.chat,
            from_user=self.tg_user,
            date=datetime.now(UTC),
            old_chat_member=ChatMemberMember(user=bot_user),
            new_chat_member=ChatMemberBanned(user=bot_user, until_date=datetime.now(UTC)),
        )
        return await self._feed(my_chat_member=event)


async def _connection_error(settings: Settings) -> str | None:
    try:
        connection = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password.get_secret_value() or None,
            database=settings.postgres_db,
            timeout=3,
        )
    except (OSError, asyncpg.PostgresError) as exc:
        return f"{type(exc).__name__}: {exc}"
    await connection.close()
    return None


@pytest.fixture(scope="session")
def settings() -> Settings:
    base = Settings()
    return base.model_copy(update={"postgres_db": f"{base.postgres_db}_test"})


@pytest.fixture(scope="session")
def migrated_db(settings: Settings) -> None:
    """Test bazasini noldan migratsiya qiladi — downgrade ham, upgrade ham sinovdan o'tadi."""
    error = asyncio.run(_connection_error(settings))
    if error:
        pytest.skip(f"Test bazasiga ({settings.postgres_db}) ulanib bo'lmadi: {error}")

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = settings.database_url
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def session_factory(settings: Settings, migrated_db: None) -> async_sessionmaker[AsyncSession]:
    # NullPool: ulanishlar saqlanmaydi, shuning uchun har bir test o'z event loop'ida
    # yangi ulanish ochadi va bitta engine butun sessiyaga yetadi.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def db(
    session_factory: async_sessionmaker[AsyncSession],
) -> async_sessionmaker[AsyncSession]:
    """Har bir test oldidan tozalangan baza."""
    async with session_factory.begin() as session:
        await session.execute(
            text("TRUNCATE notifications, favorites, users, matches, teams, external_refs")
        )
    return session_factory


@pytest.fixture
async def redis() -> AsyncIterator[FakeAsyncRedis]:
    """Xotiradagi Redis: har bir testga yangi va bo'sh."""
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def schedule(
    redis: FakeAsyncRedis, db: async_sessionmaker[AsyncSession], settings: Settings
) -> ScheduleCache:
    return ScheduleCache(redis, db, settings.tz)


@pytest.fixture(scope="session")
def names() -> TeamNames:
    return TeamNames()


@pytest.fixture(scope="session")
def i18n() -> I18n:
    return I18n("uz")


@pytest.fixture
def bot() -> Bot:
    return Bot(f"{BOT_ID}:TEST", session=RecordingSession())


@pytest.fixture(scope="session")
def dispatcher(
    session_factory: async_sessionmaker[AsyncSession], i18n: I18n, names: TeamNames
) -> Dispatcher:
    # Sessiyaga bitta: aiogram routerlari faqat bitta Dispatcher'ga ulanadi.
    # schedule har bir testda make_chat ichida almashtiriladi (u testning Redis'iga bog'liq).
    return create_dispatcher(
        storage=MemoryStorage(),
        session_factory=session_factory,
        i18n=i18n,
        schedule=None,
        names=names,
    )


@pytest.fixture
def make_chat(
    dispatcher: Dispatcher, bot: Bot, schedule: ScheduleCache
) -> Callable[..., PrivateChat]:
    dispatcher["schedule"] = schedule
    # Dispatcher sessiyaga bitta, shuning uchun suhbat holatlari har test oldidan tozalanadi.
    dispatcher.fsm.storage.storage.clear()

    def factory(**kwargs) -> PrivateChat:
        return PrivateChat(dispatcher, bot, **kwargs)

    return factory


@pytest.fixture
async def chat(make_chat: Callable[..., PrivateChat]) -> PrivateChat:
    """O'zbek tilini tanlab bo'lgan foydalanuvchi. Yangi foydalanuvchi uchun make_chat() kerak."""
    chat = make_chat()
    await chat.choose_language("uz")
    return chat
