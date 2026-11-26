from datetime import timedelta

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, SetMyCommands
from sqlalchemy import func, select

from factories import match
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
    assert menu_buttons(sent[0]) == [t("menu-matches"), t("menu-favorites"), t("menu-language")]

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


async def test_unknown_text_gets_hint_with_menu(chat, i18n):
    sent = await chat.send("salom")

    assert texts(sent) == [i18n.translate("uz", "unknown-message")]
    assert len(menu_buttons(sent[0])) == 3


# --- Yaqin o'yinlar


async def store(db, *items):
    async with db.begin() as session:
        await upsert_matches(session, "fake", items)


def nav_targets(message) -> list[str]:
    return [b.callback_data for row in message.reply_markup.inline_keyboard for b in row]


def finished(external_id: str, kickoff_at, home: str, away: str, **kwargs):
    return match(
        external_id, kickoff_at, home, away, status=MatchStatus.FINISHED, score=(2, 1), **kwargs
    )


async def test_matches_today_are_shown_with_the_next_match_day(chat, db, schedule):
    today = schedule.today()
    start, _ = day_bounds(today, schedule.tz)
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
    assert "✅ Real Madrid <b>2:1</b> Barselona" in lines
    assert sum(line.startswith("⚽ <b>") for line in lines) == 2
    assert any("Liverpul — Everton" in line for line in lines)
    assert "Arsenal" not in sent.text
    # Tugma ko'rsatilgan ikki kundan keyingi o'yin kuniga olib boradi.
    assert nav_targets(sent) == [f"day:{(today + timedelta(days=5)).isoformat()}"]


async def test_no_matches_today_starts_from_nearest_match_day(chat, db, schedule):
    today = schedule.today()
    start, _ = day_bounds(today, schedule.tz)
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
    assert "Real Madrid — Barselona" in sent.text
    assert "Liverpul — Everton" in sent.text
    assert "Manchester Siti" not in sent.text
    assert sent.text.index("Real Madrid") < sent.text.index("Liverpul")
    assert nav_targets(sent) == [
        f"day:{(today - timedelta(days=1)).isoformat()}",
        f"day:{(today + timedelta(days=6)).isoformat()}",
    ]


async def test_single_upcoming_match_day(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(db, match("m1", start + timedelta(days=2, hours=12)))

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    assert sum(line.startswith("⚽ <b>") for line in sent.text.split("\n")) == 1
    assert sent.reply_markup is None


async def test_nothing_upcoming(chat, db, schedule):
    today = schedule.today()
    start, _ = day_bounds(today, schedule.tz)
    await store(db, finished("old", start - timedelta(hours=12), "Arsenal", "Everton"))

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    assert sent.text == "<b>⚽ Yaqin o'yinlar</b>\n\nYaqin kunlarda o'yin yo'q."
    assert nav_targets(sent) == [f"day:{(today - timedelta(days=1)).isoformat()}"]


async def test_day_button_shows_that_single_day(chat, db, schedule):
    today = schedule.today()
    start, _ = day_bounds(today, schedule.tz)
    tomorrow = today + timedelta(days=1)
    await store(
        db,
        match("m1", start + timedelta(days=1, hours=12), "Liverpool", "Everton"),
        match("m2", start + timedelta(days=2, hours=12), "Arsenal", "Manchester City"),
    )

    assert await chat.press(f"day:{tomorrow.isoformat()}") == []

    answer, edit = chat.requests
    assert isinstance(answer, AnswerCallbackQuery)
    assert isinstance(edit, EditMessageText)
    assert edit.text.startswith("⚽ <b>Ertaga, ")
    assert "Liverpul — Everton" in edit.text
    assert "Arsenal" not in edit.text
    # O'rtadagi tugma asosiy ro'yxatga qaytaradi.
    assert nav_targets(edit) == ["upcoming", f"day:{(today + timedelta(days=2)).isoformat()}"]


async def test_back_button_returns_to_upcoming_list(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        match("m1", start + timedelta(days=1, hours=12), "Liverpool", "Everton"),
        match("m2", start + timedelta(days=2, hours=12), "Arsenal", "Manchester City"),
    )

    await chat.press("upcoming")

    edit = chat.requests[-1]
    assert isinstance(edit, EditMessageText)
    assert "Liverpul — Everton" in edit.text
    assert "Arsenal — Manchester Siti" in edit.text


@pytest.mark.parametrize("data", ["day:2020-01-01", "day:2099-01-01", "day:bugun-emas"])
async def test_stale_or_broken_day_button_shows_upcoming_list(chat, db, schedule, data):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(db, match("m1", start + timedelta(days=1, hours=12), "Liverpool", "Everton"))

    await chat.press(data)

    edit = chat.requests[-1]
    assert isinstance(edit, EditMessageText)
    assert "Liverpul — Everton" in edit.text


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
