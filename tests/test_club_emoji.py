from datetime import UTC, datetime, timedelta
from io import BytesIO

import httpx
import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import (
    AddStickerToSet,
    CreateNewStickerSet,
    DeleteStickerFromSet,
    GetStickerSet,
)
from PIL import Image
from sqlalchemy import select, update

from factories import BOT_USERNAME, logo_url, match
from golli.db.matches import upsert_matches
from golli.db.models import Team
from golli.services import club_emoji
from golli.services.club_emoji import ClubEmojiSyncer, to_emoji_png

NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 28, 15, 0, tzinfo=UTC)
OWNER = 777
FIRST_SET = f"clubs1_by_{BOT_USERNAME}"


def picture(size: tuple[int, int] = (143, 143)) -> bytes:
    output = BytesIO()
    Image.new("RGBA", size, (200, 20, 20, 255)).save(output, "PNG")
    return output.getvalue()


class Logos:
    """Logotip yuklash o'rniga: so'ralgan havolalarni yozib boradi."""

    def __init__(self) -> None:
        self.requested: list[str] = []
        self.broken: set[str] = set()

    async def __call__(self, url: str) -> bytes:
        self.requested.append(url)
        if url in self.broken:
            raise httpx.ConnectError("sinov xatosi")
        return picture()


@pytest.fixture
def logos() -> Logos:
    return Logos()


@pytest.fixture
def syncer(bot, db, schedule, logos) -> ClubEmojiSyncer:
    return ClubEmojiSyncer(bot, db, schedule, OWNER, fetch_logo=logos)


@pytest.fixture
async def clubs(db) -> None:
    async with db.begin() as session:
        await upsert_matches(session, "fake", [match("m1", KICKOFF, "Arsenal", "Manchester City")])


async def emoji_ids(db) -> dict[str, str | None]:
    async with db() as session:
        return {team.name: team.emoji_id for team in await session.scalars(select(Team))}


def requests_of(bot, kind) -> list:
    return [request for request in bot.session.requests if isinstance(request, kind)]


# --- Rasm


def test_logo_becomes_100x100_png_keeping_its_proportions():
    image = Image.open(BytesIO(to_emoji_png(picture((200, 100)))))

    assert (image.format, image.size, image.mode) == ("PNG", (100, 100), "RGBA")
    # Yotiq rasm: tepasi va pasti shaffof, o'rtasi to'la.
    assert image.getpixel((50, 5))[3] == 0
    assert image.getpixel((50, 50)) == (200, 20, 20, 255)
    assert image.getpixel((2, 50))[3] == 255


def test_small_logo_is_enlarged_to_fill_the_emoji():
    image = Image.open(BytesIO(to_emoji_png(picture((40, 40)))))

    assert image.size == (100, 100)
    assert image.getpixel((3, 3))[3] == 255


# --- To'plam


async def test_first_run_creates_the_set_and_stores_emoji_ids(syncer, bot, db, schedule, clubs):
    await syncer.tick(NOW)

    [created] = requests_of(bot, CreateNewStickerSet)
    assert (created.name, created.user_id, created.sticker_type) == (
        FIRST_SET,
        OWNER,
        "custom_emoji",
    )
    assert [(s.format, s.emoji_list) for s in created.stickers] == [("static", ["⚽"])]
    # Birinchi emoji to'plam bilan birga yaratiladi, qolganlari unga qo'shiladi.
    assert len(requests_of(bot, AddStickerToSet)) == 1

    ids = await emoji_ids(db)
    assert sorted(ids.values()) == sorted(
        s.custom_emoji_id for s in bot.session.sticker_sets[FIRST_SET]
    )
    assert ids["Arsenal"] != ids["Manchester City"]

    # Ro'yxatlar keshdan o'qiladi: yangi emojilar keshga ham tushgan.
    [cached] = await schedule.get_day(KICKOFF.astimezone(schedule.tz).date())
    assert (cached.home_emoji, cached.away_emoji) == (ids["Arsenal"], ids["Manchester City"])


async def test_nothing_to_do_means_no_telegram_calls(syncer, bot, clubs):
    await syncer.tick(NOW)
    made = len(bot.session.requests)

    await syncer.tick(NOW + timedelta(minutes=1))

    assert len(bot.session.requests) == made


async def test_new_club_is_added_to_the_existing_set_after_restart(bot, db, schedule, logos, clubs):
    await ClubEmojiSyncer(bot, db, schedule, OWNER, fetch_logo=logos).tick(NOW)
    async with db.begin() as session:
        await upsert_matches(session, "fake", [match("m2", KICKOFF, "Liverpool", "Arsenal")])

    # Worker qayta ishga tushgan: to'plam holati Telegram'dan o'qiladi.
    await ClubEmojiSyncer(bot, db, schedule, OWNER, fetch_logo=logos).tick(NOW)

    assert len(requests_of(bot, CreateNewStickerSet)) == 1
    assert len(bot.session.sticker_sets[FIRST_SET]) == 3
    assert logos.requested.count(logo_url("Arsenal")) == 1
    assert None not in (await emoji_ids(db)).values()


async def test_disabled_without_owner(bot, db, schedule, logos, clubs):
    await ClubEmojiSyncer(bot, db, schedule, None, fetch_logo=logos).tick(NOW)

    assert bot.session.requests == []
    assert logos.requested == []
    assert set((await emoji_ids(db)).values()) == {None}


async def test_club_without_logo_is_skipped(syncer, bot, db, clubs):
    async with db.begin() as session:
        await session.execute(update(Team).where(Team.name == "Arsenal").values(logo_url=None))

    await syncer.tick(NOW)

    ids = await emoji_ids(db)
    assert ids["Arsenal"] is None
    assert ids["Manchester City"] is not None


async def test_at_most_one_batch_per_tick(syncer, db, clubs, monkeypatch):
    monkeypatch.setattr(club_emoji, "BATCH", 1)

    await syncer.tick(NOW)
    assert list((await emoji_ids(db)).values()).count(None) == 1

    await syncer.tick(NOW + timedelta(minutes=1))
    assert None not in (await emoji_ids(db)).values()


async def test_full_set_rolls_over_to_the_next_one(syncer, bot, db, clubs, monkeypatch):
    monkeypatch.setattr(club_emoji, "SET_LIMIT", 1)

    await syncer.tick(NOW)

    assert {name: len(items) for name, items in bot.session.sticker_sets.items()} == {
        FIRST_SET: 1,
        f"clubs2_by_{BOT_USERNAME}": 1,
    }
    assert None not in (await emoji_ids(db)).values()


async def test_leftover_emoji_unknown_to_the_database_is_removed(syncer, bot, db, clubs):
    # Avvalgi urinish emoji qo'shgan, lekin bazaga yozishga ulgurmagan.
    leftover = bot.session.add_sticker(FIRST_SET)

    await syncer.tick(NOW)

    assert [request.sticker for request in requests_of(bot, DeleteStickerFromSet)] == [
        leftover.file_id
    ]
    in_set = {sticker.custom_emoji_id for sticker in bot.session.sticker_sets[FIRST_SET]}
    assert in_set == set((await emoji_ids(db)).values())
    # To'plam bo'shab qolgan bo'lsa ham mavjud: qayta yaratilmaydi, unga qo'shiladi.
    assert requests_of(bot, CreateNewStickerSet) == []


# --- Xatolar


async def test_broken_logo_does_not_block_other_clubs(syncer, db, logos, clubs):
    logos.broken.add(logo_url("Arsenal"))

    await syncer.tick(NOW)
    ids = await emoji_ids(db)
    assert ids["Arsenal"] is None
    assert ids["Manchester City"] is not None

    # Buzuq logotipga har daqiqada emas, keyinroq qayta uriniladi.
    await syncer.tick(NOW + timedelta(minutes=1))
    assert logos.requested.count(logo_url("Arsenal")) == 1

    logos.broken.clear()
    await syncer.tick(NOW + club_emoji.BROKEN_LOGO_DELAY + timedelta(minutes=1))
    assert (await emoji_ids(db))["Arsenal"] is not None


async def test_flood_limit_pauses_then_continues(syncer, bot, db, clubs):
    bot.session.method_failures[AddStickerToSet] = lambda method: TelegramRetryAfter(
        method=method, message="Too Many Requests", retry_after=30
    )

    await syncer.tick(NOW)
    assert list((await emoji_ids(db)).values()).count(None) == 1

    # Telegram aytgan vaqt o'tmaguncha hech narsa so'ralmaydi.
    made = len(bot.session.requests)
    await syncer.tick(NOW + timedelta(seconds=10))
    assert len(bot.session.requests) == made

    del bot.session.method_failures[AddStickerToSet]
    await syncer.tick(NOW + timedelta(seconds=31))
    assert None not in (await emoji_ids(db)).values()
    assert len(bot.session.sticker_sets[FIRST_SET]) == 2


async def test_telegram_outage_is_retried_later(syncer, bot, db, clubs):
    bot.session.method_failures[GetStickerSet] = lambda method: TelegramNetworkError(
        method=method, message="Connection reset"
    )

    await syncer.tick(NOW)
    assert set((await emoji_ids(db)).values()) == {None}

    del bot.session.method_failures[GetStickerSet]
    await syncer.tick(NOW + timedelta(minutes=5))
    assert set((await emoji_ids(db)).values()) == {None}  # hali kutish vaqti

    await syncer.tick(NOW + club_emoji.RETRY_DELAY + timedelta(minutes=1))
    assert None not in (await emoji_ids(db)).values()
