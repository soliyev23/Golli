from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, SetMyCommands
from sqlalchemy import func, select

from factories import match
from golli.bot.handlers.matches import recent_text, upcoming_text
from golli.db.matches import upsert_matches
from golli.db.models import User
from golli.providers.base import MatchStatus
from golli.services.days import day_bounds


async def get_user(db, user_id: int) -> User | None:
    async with db() as session:
        return await session.get(User, user_id)


async def count_users(db) -> int:
    async with db() as session:
        return await session.scalar(select(func.count()).select_from(User))


def texts(sent: list[SendMessage]) -> list[str]:
    return [message.text for message in sent]


def menu_buttons(message: SendMessage) -> list[str]:
    return [button.text for row in message.reply_markup.keyboard for button in row]


def is_language_prompt(sent: list[SendMessage]) -> bool:
    return len(sent) == 1 and [
        button.callback_data for row in sent[0].reply_markup.inline_keyboard for button in row
    ] == ["lang:uz", "lang:ru", "lang:en"]


# --- Til tanlash


async def test_first_start_asks_language(make_chat, db):
    chat = make_chat()

    sent = await chat.send("/start")

    assert texts(sent) == ["Tilni tanlang\nВыберите язык\nChoose a language"]
    buttons = [button.text for row in sent[0].reply_markup.inline_keyboard for button in row]
    assert buttons == ["🇺🇿 O'zbekcha", "🇷🇺 Русский", "🇬🇧 English"]
    assert is_language_prompt(sent)

    user = await get_user(db, chat.user_id)
    assert user.lang is None
    assert user.is_active is True


async def test_any_message_before_choice_asks_language(make_chat, i18n):
    chat = make_chat()

    for text in ("salom", "/help", i18n.translate("uz", "menu-matches")):
        assert is_language_prompt(await chat.send(text))


@pytest.mark.parametrize("code", ["uz", "ru", "en"])
async def test_choosing_language_saves_it_and_welcomes(make_chat, db, i18n, code):
    chat = make_chat()
    await chat.send("/start")

    sent = await chat.choose_language(code)

    t = i18n.translator(code)
    assert (await get_user(db, chat.user_id)).lang == code
    assert texts(sent) == [t("start-welcome", name="Ali")]
    assert menu_buttons(sent[0]) == [
        t("menu-matches"),
        t("menu-recent"),
        t("menu-favorites"),
        t("menu-language"),
    ]

    answer, edit, _, commands = chat.requests
    assert isinstance(answer, AnswerCallbackQuery)
    assert isinstance(edit, EditMessageText) and edit.text == t("lang-set")
    assert isinstance(commands, SetMyCommands) and commands.scope.chat_id == chat.user_id
    assert [c.description for c in commands.commands] == [
        t("cmd-start"),
        t("cmd-lang"),
        t("cmd-help"),
    ]


async def test_start_after_choice_shows_welcome_in_chosen_language(make_chat, i18n):
    chat = make_chat()
    await chat.choose_language("ru")

    sent = await chat.send("/start")

    assert texts(sent) == [i18n.translate("ru", "start-welcome", name="Ali")]


async def test_language_can_be_changed_later(chat, db, i18n):
    for trigger in (i18n.translate("uz", "menu-language"), "/lang"):
        assert is_language_prompt(await chat.send(trigger))

    await chat.choose_language("en")

    assert (await get_user(db, chat.user_id)).lang == "en"
    assert texts(await chat.send("/help")) == [i18n.translate("en", "help-text")]


async def test_unknown_language_code_is_ignored(chat, db):
    sent = await chat.press("lang:xx")

    assert sent == []
    assert [type(request) for request in chat.requests] == [AnswerCallbackQuery]
    assert (await get_user(db, chat.user_id)).lang == "uz"


# --- /start, /help va menyu


async def test_repeated_start_keeps_single_user(chat, db):
    await chat.send("/start")
    await chat.send("/start")

    assert await count_users(db) == 1


async def test_name_is_html_escaped(make_chat):
    chat = make_chat(first_name="<b>Ali</b> & Vali")
    await chat.choose_language("uz")

    sent = await chat.send("/start")

    assert "&lt;b&gt;Ali&lt;/b&gt; &amp; Vali" in sent[0].text
    assert "<b>Ali</b>" not in sent[0].text


async def test_help(chat, i18n):
    sent = await chat.send("/help")

    assert texts(sent) == [i18n.translate("uz", "help-text")]


@pytest.mark.parametrize("code", ["uz", "ru", "en"])
async def test_menu_buttons_are_recognised_in_every_language(make_chat, i18n, code):
    chat = make_chat()
    await chat.choose_language(code)
    t = i18n.translator(code)

    [favorites] = await chat.send(t("menu-favorites"))
    assert favorites.text.startswith(t("favorites-title"))
    [upcoming] = await chat.send(t("menu-matches"))
    assert upcoming.text.endswith(t("matches-none-upcoming"))
    [recent] = await chat.send(t("menu-recent"))
    assert recent.text.endswith(t("matches-none-recent"))


async def test_unknown_text_gets_hint_with_menu(chat, i18n):
    sent = await chat.send("salom")

    assert texts(sent) == [i18n.translate("uz", "unknown-message")]
    assert len(menu_buttons(sent[0])) == 4


# --- Yaqin o'yinlar


async def store(db, *items):
    async with db.begin() as session:
        await upsert_matches(session, "fake", items)


def finished(external_id: str, kickoff_at, home: str, away: str, **kwargs):
    return match(
        external_id, kickoff_at, home, away, status=MatchStatus.FINISHED, score=(2, 1), **kwargs
    )


def day_titles(text: str) -> int:
    return sum(line.startswith("⚽ <b>") for line in text.split("\n"))


async def test_matches_today_are_shown_with_the_next_match_day(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        finished(
            "m1", start + timedelta(minutes=1), "Real Madrid", "Barcelona", competition="laliga"
        ),
        # Ertaga o'yin yo'q; keyingi o'yin kuni — indinga.
        match("m2", start + timedelta(days=2, hours=12), "Liverpool", "Everton"),
        match("m3", start + timedelta(days=5, hours=12), "Arsenal", "Manchester City"),
    )

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    lines = sent.text.split("\n")
    assert lines[0].startswith("⚽ <b>Bugun, ")
    assert "Real Madrid <b>2:1</b> Barselona" in lines
    assert day_titles(sent.text) == 2
    assert any("Liverpul – Everton" in line for line in lines)
    assert "Arsenal" not in sent.text


async def test_no_matches_today_starts_from_nearest_match_day(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        finished("old", start - timedelta(days=1, hours=-12), "Arsenal", "Everton"),
        match(
            "m1",
            start + timedelta(days=3, hours=12),
            "Real Madrid",
            "Barcelona",
            competition="laliga",
        ),
        match("m2", start + timedelta(days=4, hours=12), "Liverpool", "Everton"),
        match("m3", start + timedelta(days=6, hours=12), "Arsenal", "Manchester City"),
    )

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    assert "Bugun" not in sent.text
    assert "Real Madrid – Barselona" in sent.text
    assert "Liverpul – Everton" in sent.text
    assert "Man Siti" not in sent.text
    assert sent.text.index("Real Madrid") < sent.text.index("Liverpul")


async def test_single_upcoming_match_day(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(db, match("m1", start + timedelta(days=2, hours=12)))

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    assert day_titles(sent.text) == 1


async def test_nothing_upcoming(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(db, finished("old", start - timedelta(hours=12), "Arsenal", "Everton"))

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    assert sent.text == "<b>⚽ Yaqin o'yinlar</b>\n\nYaqin kunlarda o'yin yo'q."


@pytest.mark.parametrize("button", ["⚽ Yaqin o'yinlar", "🏁 Oxirgi o'yinlar"])
async def test_lists_have_no_day_buttons_and_refresh_the_menu(chat, db, schedule, button):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        finished("old", start - timedelta(hours=12), "Arsenal", "Everton"),
        finished("older", start - timedelta(days=2, hours=12), "Liverpool", "Everton"),
        match("m1", start + timedelta(days=1, hours=12), "Liverpool", "Everton"),
        match("m2", start + timedelta(days=3, hours=12), "Arsenal", "Manchester City"),
    )

    [sent] = await chat.send(button)

    # Xabar ostida kundan kunga o'tish tugmalari yo'q; javob bilan asosiy menyu keladi.
    assert menu_buttons(sent) == [
        "⚽ Yaqin o'yinlar",
        "🏁 Oxirgi o'yinlar",
        "⭐ Sevimli klublar",
        "🌐 Til",
    ]


@pytest.mark.parametrize("data", ["day:2026-11-26", "day:bugun-emas", "upcoming"])
async def test_button_left_in_an_old_message_turns_it_into_the_current_list(
    chat, db, schedule, data
):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(db, match("m1", start + timedelta(days=1, hours=12), "Liverpool", "Everton"))

    assert await chat.press(data) == []

    answer, edit = chat.requests
    assert isinstance(answer, AnswerCallbackQuery)
    assert isinstance(edit, EditMessageText)
    assert "Liverpul – Everton" in edit.text
    assert edit.reply_markup is None


# --- Oxirgi o'yinlar


async def test_recent_shows_the_last_two_match_days_newest_first(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        finished("d9", start - timedelta(days=9, hours=-12), "Arsenal", "Manchester City"),
        finished("d5", start - timedelta(days=5, hours=-12), "Liverpool", "Everton"),
        # Orada o'yinsiz kunlar bor: ular tashlab ketiladi.
        finished(
            "d2",
            start - timedelta(days=2, hours=-12),
            "Real Madrid",
            "Barcelona",
            competition="laliga",
        ),
        match("next", start + timedelta(days=1, hours=12), "Arsenal", "Everton"),
    )

    [sent] = await chat.send("🏁 Oxirgi o'yinlar")

    assert day_titles(sent.text) == 2
    assert "Real Madrid <b>2:1</b> Barselona" in sent.text
    assert "Liverpul <b>2:1</b> Everton" in sent.text
    assert sent.text.index("Real Madrid") < sent.text.index("Liverpul")
    assert "Man Siti" not in sent.text
    # Natijalar ro'yxatida soat yo'q, demak vaqt mintaqasi haqida izoh ham yo'q.
    assert "Toshkent" not in sent.text


async def test_nothing_recent(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(db, match("next", start + timedelta(days=1, hours=12)))

    [sent] = await chat.send("🏁 Oxirgi o'yinlar")

    assert sent.text == "<b>🏁 Oxirgi o'yinlar</b>\n\nSo'nggi kunlarda o'yin bo'lmadi."


# --- Yarim tun atrofida

TASHKENT = ZoneInfo("Asia/Tashkent")


def tashkent(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TASHKENT)


async def upcoming(schedule, i18n, names, now: datetime) -> str:
    await schedule.rebuild(now)
    return await upcoming_text(schedule, now, i18n.translator("uz"), names)


async def recent(schedule, i18n, names, now: datetime) -> str:
    await schedule.rebuild(now)
    return await recent_text(schedule, now, i18n.translator("uz"), names)


async def test_night_match_is_listed_under_its_own_date(db, schedule, i18n, names):
    await store(
        db,
        match("sat", tashkent(28, 20), "Arsenal", "Manchester City"),
        match("night", tashkent(29, 1), "Real Madrid", "Barcelona", competition="laliga"),
    )

    lines = (await upcoming(schedule, i18n, names, tashkent(28, 12))).split("\n")

    saturday = lines.index("⚽ <b>Bugun, 28-noyabr, shanba</b>")
    sunday = lines.index("⚽ <b>Ertaga, 29-noyabr, yakshanba</b>")
    assert saturday < lines.index("20:00 Arsenal – Man Siti") < sunday
    assert lines.index("01:00 Real Madrid – Barselona") > sunday
    assert "🌙" not in "".join(lines)


async def test_match_still_in_play_after_midnight_stays_in_the_list(db, schedule, i18n, names):
    await store(
        db,
        finished("early", tashkent(28, 17), "Liverpool", "Everton"),
        match("late", tashkent(28, 23), status=MatchStatus.LIVE, score=(1, 0)),
        match("night", tashkent(29, 1), "Real Madrid", "Barcelona", competition="laliga"),
        match("monday", tashkent(30, 20), "Club Brugge KV", "Liverpool", competition="ucl"),
    )

    # Yakshanba 00:30: shanba kungi o'yin hali ketmoqda — ro'yxat kechadan boshlanadi.
    text = await upcoming(schedule, i18n, names, tashkent(29, 0, 30))
    assert text.startswith("⚽ <b>Kecha, 28-noyabr, shanba</b>")
    assert "🔴 Arsenal <b>1:0</b> Man Siti" in text
    assert "⚽ <b>Bugun, 29-noyabr, yakshanba</b>" in text
    assert "Bryugge" not in text

    # O'yin tugagach ro'yxat yana bugundan boshlanadi.
    await store(db, finished("late", tashkent(28, 23), "Arsenal", "Manchester City"))
    text = await upcoming(schedule, i18n, names, tashkent(29, 1, 30))
    assert text.startswith("⚽ <b>Bugun, 29-noyabr, yakshanba</b>")
    assert "Kecha" not in text
    assert "Bryugge – Liverpul" in text


async def test_stuck_match_does_not_hold_yesterday_in_the_list(db, schedule, i18n, names):
    # Holati yangilanmay qolgan kechagi o'yin ro'yxatni ertasi kuni ham kechadan boshlatmaydi.
    await store(
        db,
        match("stuck", tashkent(28, 17), status=MatchStatus.LIVE, score=(1, 0)),
        match("sunday", tashkent(29, 19), "Liverpool", "Everton"),
    )

    text = await upcoming(schedule, i18n, names, tashkent(29, 10))

    assert text.startswith("⚽ <b>Bugun, 29-noyabr, yakshanba</b>")


async def test_recent_keeps_night_match_under_its_own_date(db, schedule, i18n, names):
    await store(
        db,
        finished("sat", tashkent(28, 20), "Arsenal", "Manchester City"),
        finished("night", tashkent(29, 1), "Real Madrid", "Barcelona", competition="laliga"),
    )

    lines = (await recent(schedule, i18n, names, tashkent(29, 12))).split("\n")

    sunday = lines.index("⚽ <b>Bugun, 29-noyabr, yakshanba</b>")
    saturday = lines.index("⚽ <b>Kecha, 28-noyabr, shanba</b>")
    assert sunday < lines.index("Real Madrid <b>2:1</b> Barselona") < saturday
    assert lines.index("Arsenal <b>2:1</b> Man Siti") > saturday


async def test_recent_lists_only_matches_that_are_over(db, schedule, i18n, names):
    await store(
        db,
        finished("early", tashkent(28, 17), "Liverpool", "Everton"),
        match("live", tashkent(28, 20), status=MatchStatus.LIVE, score=(1, 0)),
        match("late", tashkent(28, 23), "Real Madrid", "Barcelona", competition="laliga"),
        match(
            "off",
            tashkent(28, 22),
            "Club Brugge KV",
            "Liverpool",
            competition="ucl",
            status=MatchStatus.POSTPONED,
        ),
        # Ertangi kun: hali hech bir o'yin tugamagan, shuning uchun ro'yxatga kirmaydi.
        match("sunday", tashkent(29, 19), "Arsenal", "Everton"),
    )

    text = await recent(schedule, i18n, names, tashkent(28, 21))

    assert text.split("\n")[0] == "⚽ <b>Bugun, 28-noyabr, shanba</b>"
    assert "Liverpul <b>2:1</b> Everton" in text
    assert "⏸ Bryugge – Liverpul · ko'chirilgan" in text
    assert "Man Siti" not in text
    assert "Real Madrid" not in text
    assert "29-noyabr" not in text


# --- Bloklash va guruhlar


async def test_block_deactivates_and_next_message_reactivates(chat, db):
    assert await chat.block() == []
    assert (await get_user(db, chat.user_id)).is_active is False

    await chat.send("/start")
    assert (await get_user(db, chat.user_id)).is_active is True


async def test_group_chat_is_ignored(make_chat, db):
    group = make_chat(chat_type="group")

    assert await group.send("/start") == []
    assert await count_users(db) == 0
