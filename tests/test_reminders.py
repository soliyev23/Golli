from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from sqlalchemy import select

from factories import FakeProvider, match
from golli.db.favorites import toggle_favorite
from golli.db.matches import upsert_matches
from golli.db.models import Match, Notification, Team, User
from golli.db.users import get_or_create_user
from golli.providers.base import MatchStatus
from golli.services.reminders import MAX_ATTEMPTS, ReminderPlanner, Sender
from golli.services.sync import Syncer

TASHKENT = ZoneInfo("Asia/Tashkent")
SATURDAY = date(2026, 11, 28)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TASHKENT)


async def store(db, *items):
    async with db.begin() as session:
        await upsert_matches(session, "fake", items)


async def add_user(db, user_id: int, *favorites: str, lang: str = "uz", active: bool = True):
    """Foydalanuvchi va uning sevimli klublari (klublar bazada bo'lishi kerak)."""
    async with db.begin() as session:
        user = await get_or_create_user(session, user_id)
        user.lang, user.is_active = lang, active
        for name in favorites:
            team_id = await session.scalar(select(Team.id).where(Team.name == name))
            await toggle_favorite(session, user_id, team_id)


async def queue(db) -> list[Notification]:
    async with db() as session:
        return list(await session.scalars(select(Notification).order_by(Notification.id)))


async def queued(db) -> list[tuple[int, str]]:
    return sorted((n.user_id, n.kind) for n in await queue(db))


def sent_messages(bot) -> list[SendMessage]:
    return [r for r in bot.session.requests if isinstance(r, SendMessage)]


@pytest.fixture
def planner(db, redis, settings) -> ReminderPlanner:
    return ReminderPlanner(db, redis, settings.tz)


@pytest.fixture
def sender(bot, db, i18n, names, settings) -> Sender:
    return Sender(bot, db, i18n, names, settings.tz)


@pytest.fixture
async def weekend(db) -> None:
    """Shanba: Arsenal — Man City 20:00, Real — Barsa tunda 01:00. Yakshanba: Liverpool."""
    await store(
        db,
        match("e1", at(28, 20), "Arsenal", "Manchester City"),
        match("l1", at(29, 1), "Real Madrid", "Barcelona", competition="laliga"),
        match("e2", at(29, 19), "Liverpool", "Everton"),
    )


# --- Ertalabki xabar


async def test_morning_reminder_goes_to_fans_of_todays_teams(db, planner, weekend):
    await add_user(db, 1, "Arsenal")
    await add_user(db, 2, "Barcelona")  # o'yini yarim tundan keyin — baribir bugungi ro'yxatda
    await add_user(db, 3, "Everton")  # ertaga o'ynaydi
    await add_user(db, 4, "Arsenal", active=False)  # botni bloklagan
    await add_user(db, 5)  # sevimli klubi yo'q

    await planner.plan(at(28, 6, 59))
    assert await queued(db) == []

    await planner.plan(at(28, 7, 0))
    assert await queued(db) == [(1, "morning"), (2, "morning")]
    assert {n.day for n in await queue(db)} == {SATURDAY}


async def test_morning_reminder_is_planned_once_a_day(db, planner, weekend):
    await add_user(db, 1, "Arsenal")
    await planner.plan(at(28, 7, 0))

    # Kun davomida klub qo'shgan foydalanuvchiga "ertalabki" xabar kech bo'lib qoladi.
    await add_user(db, 2, "Manchester City")
    await planner.plan(at(28, 7, 1))
    await planner.plan(at(28, 11, 0))
    assert await queued(db) == [(1, "morning")]

    # Ertasi kuni — yangi xabarlar.
    await add_user(db, 3, "Everton")
    await planner.plan(at(29, 7, 0))
    assert (3, "morning") in await queued(db)


async def test_one_morning_message_even_with_several_clubs(db, planner, weekend):
    await add_user(db, 1, "Arsenal", "Manchester City", "Real Madrid")

    await planner.plan(at(28, 7, 0))

    assert await queued(db) == [(1, "morning")]


async def test_no_morning_reminder_when_planner_starts_late(db, planner, weekend):
    await add_user(db, 1, "Arsenal")

    await planner.plan(at(28, 12, 0))

    assert await queued(db) == []


async def test_postponed_match_gives_no_morning_reminder(db, planner):
    await store(db, match("e1", at(28, 20), status=MatchStatus.POSTPONED))
    await add_user(db, 1, "Arsenal")

    await planner.plan(at(28, 7, 0))

    assert await queued(db) == []


# --- O'yin oldidan


async def test_pre_match_reminder_one_hour_before_kickoff(db, planner, weekend):
    await add_user(db, 1, "Arsenal")
    await add_user(db, 2, "Manchester City")
    await add_user(db, 3, "Arsenal", "Manchester City")  # ikkala jamoa ham sevimli
    await add_user(db, 4, "Liverpool")  # boshqa o'yin
    await add_user(db, 5, "Arsenal", active=False)

    await planner.plan(at(28, 18, 59))
    assert await queued(db) == []

    await planner.plan(at(28, 19, 0))
    assert await queued(db) == [(1, "pre_match"), (2, "pre_match"), (3, "pre_match")]

    # Keyingi aylanishlarda takrorlanmaydi.
    await planner.plan(at(28, 19, 1))
    await planner.plan(at(28, 19, 30))
    assert len(await queue(db)) == 3


async def test_pre_match_for_after_midnight_kickoff(db, planner, weekend):
    await add_user(db, 1, "Real Madrid")

    await planner.plan(at(29, 0, 0))

    assert await queued(db) == [(1, "pre_match")]


# --- Natija


async def test_result_is_queued_when_match_finishes(db, planner, weekend):
    await add_user(db, 1, "Arsenal")
    await add_user(db, 2, "Liverpool")

    await planner.plan(at(28, 21, 0))  # o'yin ketmoqda
    assert await queued(db) == []

    await store(db, match("e1", at(28, 20), status=MatchStatus.FINISHED, score=(2, 1)))
    await planner.plan(at(28, 21, 55))
    assert await queued(db) == [(1, "result")]

    await planner.plan(at(28, 21, 56))
    assert len(await queue(db)) == 1


async def test_old_results_are_not_announced(db, planner):
    await store(db, match("e1", at(28, 20), status=MatchStatus.FINISHED, score=(2, 1)))
    await add_user(db, 1, "Arsenal")

    # Worker uzoq to'xtab qolgan: o'yin 7 soat oldin boshlangan.
    await planner.plan(at(29, 3, 0))

    assert await queued(db) == []


# --- Yuborish


async def test_pre_match_message(db, planner, sender, bot, weekend):
    await add_user(db, 1, "Arsenal")
    await add_user(db, 2, "Manchester City", lang="ru")
    await planner.plan(at(28, 19, 0))

    processed, pause = await sender.process_batch(at(28, 19, 0))

    assert (processed, pause) == (2, 0.0)
    messages = {m.chat_id: m for m in sent_messages(bot)}
    assert messages[1].text.split("\n") == [
        "⏰ <b>O'yinga 1 soat qoldi</b>",
        "",
        "<b>Arsenal — Manchester Siti</b>",
        messages[1].text.split("\n")[3],
    ]
    assert messages[1].text.endswith(" APL · 20:00")
    assert messages[2].text.startswith(
        "⏰ <b>До матча остался 1 час</b>\n\n<b>Арсенал — Манчестер Сити</b>"
    )
    assert not messages[1].disable_notification

    assert [(n.status, n.sent_at) for n in await queue(db)] == [("sent", at(28, 19, 0))] * 2
    # Navbat bo'sh: ikkinchi marta hech narsa ketmaydi.
    assert await sender.process_batch(at(28, 19, 1)) == (0, 0.0)
    assert len(sent_messages(bot)) == 2


async def test_late_pre_match_message_tells_minutes_left(db, planner, sender, bot, weekend):
    await add_user(db, 1, "Arsenal")
    await planner.plan(at(28, 19, 0))

    await sender.process_batch(at(28, 19, 35))

    assert sent_messages(bot)[0].text.startswith("⏰ <b>O'yinga 25 daqiqa qoldi</b>")


async def test_pre_match_message_is_dropped_after_kickoff(db, planner, sender, bot, weekend):
    await add_user(db, 1, "Arsenal")
    await planner.plan(at(28, 19, 0))

    await sender.process_batch(at(28, 20, 5))

    assert sent_messages(bot) == []
    assert [n.status for n in await queue(db)] == ["skipped"]


@pytest.mark.parametrize(("hour", "silent"), [(22, False), (23, True), (3, True), (8, False)])
async def test_result_message_is_silent_at_night(db, planner, sender, bot, hour, silent):
    now = at(28, hour, 30)
    await store(
        db,
        match(
            "u1",
            now - timedelta(hours=2),
            "Real Madrid",
            "Arsenal",
            competition="ucl",
            status=MatchStatus.FINISHED,
            score=(1, 1),
            penalties=(4, 3),
        ),
    )
    await add_user(db, 1, "Arsenal")
    await planner.plan(now)

    await sender.process_batch(now)

    [message] = sent_messages(bot)
    assert message.text == (
        "🏁 <b>O'yin tugadi</b>\n\nReal Madrid <b>1:1</b> Arsenal (pen. 4:3)\n🏆 Chempionlar ligasi"
    )
    assert bool(message.disable_notification) is silent


async def test_morning_message_lists_all_favourite_matches(db, planner, sender, bot, weekend, i18n):
    await add_user(db, 1, "Arsenal", "Real Madrid", "Everton")
    await planner.plan(at(28, 7, 0))

    await sender.process_batch(at(28, 7, 0))

    [message] = sent_messages(bot)
    assert message.text == "\n".join(
        [
            "☀️ <b>Bugun sevimli klubingiz o'ynaydi</b>",
            "",
            f"<b>{i18n.translate('uz', 'competition-epl')}</b>",
            "20:00  Arsenal — Manchester Siti",
            "",
            "<b>🇪🇸 La Liga</b>",
            "🌙 01:00  Real Madrid — Barselona",
            "",
            "🌙 Yarim tundan keyin (29-noyabr)",
            "",
            "🕐 Vaqt — Toshkent bo'yicha",
        ]
    )
    assert not message.disable_notification


async def test_blocked_user_is_deactivated(db, planner, sender, bot, weekend):
    await add_user(db, 1, "Arsenal")
    await planner.plan(at(28, 19, 0))
    bot.session.failures[1] = lambda method: TelegramForbiddenError(
        method=method, message="Forbidden: bot was blocked by the user"
    )

    await sender.process_batch(at(28, 19, 0))

    [notification] = await queue(db)
    assert notification.status == "failed"
    assert "blocked" in notification.error
    async with db() as session:
        assert (await session.get(User, 1)).is_active is False
    # Bloklagan foydalanuvchiga keyingi eslatmalar rejalanmaydi.
    await store(db, match("e1", at(28, 20), status=MatchStatus.FINISHED, score=(1, 0)))
    await planner.plan(at(28, 22, 0))
    assert len(await queue(db)) == 1


async def test_flood_limit_keeps_message_and_asks_to_wait(db, planner, sender, bot, weekend):
    await add_user(db, 1, "Arsenal")
    await planner.plan(at(28, 19, 0))
    bot.session.failures[1] = lambda method: TelegramRetryAfter(
        method=method, message="Too Many Requests", retry_after=7
    )

    assert await sender.process_batch(at(28, 19, 0)) == (1, 7.0)

    [notification] = await queue(db)
    assert (notification.status, notification.attempts) == ("pending", 0)
    assert notification.send_after == at(28, 19, 0) + timedelta(seconds=7)
    # Kutish vaqti o'tmaguncha qayta urinilmaydi, o'tgach — yuboriladi.
    del bot.session.failures[1]
    assert await sender.process_batch(at(28, 19, 0) + timedelta(seconds=3)) == (0, 0.0)
    assert await sender.process_batch(at(28, 19, 0) + timedelta(seconds=8)) == (1, 0.0)
    assert [n.status for n in await queue(db)] == ["sent"]


async def test_network_error_is_retried_then_given_up(db, planner, sender, bot, weekend):
    await add_user(db, 1, "Arsenal")
    await planner.plan(at(28, 19, 0))
    bot.session.failures[1] = lambda method: TelegramNetworkError(
        method=method, message="Connection reset"
    )

    now = at(28, 19, 0)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert (await sender.process_batch(now))[0] == 1
        [notification] = await queue(db)
        assert notification.attempts == attempt
        now += timedelta(minutes=2)

    assert notification.status == "failed"
    assert await sender.process_batch(now) == (0, 0.0)


async def test_user_gets_one_message_per_batch(db, planner, sender, bot):
    # Ikki sevimli klubning o'yini bir vaqtda boshlanadi: ikkita xabar, ketma-ket to'plamlarda.
    await store(
        db,
        match("e1", at(28, 20), "Arsenal", "Manchester City"),
        match("e2", at(28, 20), "Liverpool", "Everton"),
    )
    await add_user(db, 1, "Arsenal", "Liverpool")
    await planner.plan(at(28, 19, 0))
    assert len(await queue(db)) == 2

    assert (await sender.process_batch(at(28, 19, 0)))[0] == 1
    assert len(sent_messages(bot)) == 1
    assert (await sender.process_batch(at(28, 19, 0)))[0] == 1
    assert len(sent_messages(bot)) == 2


# --- To'liq oqim: provayder -> baza -> navbat -> Telegram


async def test_full_flow_from_provider_to_telegram(
    db, schedule, redis, settings, planner, sender, bot
):
    provider = FakeProvider()
    syncer = Syncer(provider, db, schedule, redis, settings.tz)
    kickoff = at(28, 20)
    provider.season["epl"] = [match("m1", kickoff)]

    async def tick(now: datetime) -> None:
        await syncer.tick(now)
        await planner.plan(now)
        await sender.process_batch(now)

    await tick(at(28, 6, 30))  # taqvim sinxronlanadi
    await add_user(db, 1, "Arsenal")

    await tick(at(28, 7, 0))
    await tick(at(28, 19, 0))
    provider.set_day(match("m1", kickoff, status=MatchStatus.LIVE, score=(1, 0), minute=10))
    await tick(kickoff + timedelta(minutes=10))
    provider.set_day(match("m1", kickoff, status=MatchStatus.FINISHED, score=(2, 1)))
    await tick(kickoff + timedelta(minutes=105))

    titles = [m.text.split("\n")[0] for m in sent_messages(bot)]
    assert titles == [
        "☀️ <b>Bugun sevimli klubingiz o'ynaydi</b>",
        "⏰ <b>O'yinga 1 soat qoldi</b>",
        "🏁 <b>O'yin tugadi</b>",
    ]
    assert "Arsenal <b>2:1</b> Manchester Siti" in sent_messages(bot)[-1].text
    async with db() as session:
        stored = await session.scalar(select(Match))
    assert stored.pre_notified_at is not None and stored.result_notified_at is not None
