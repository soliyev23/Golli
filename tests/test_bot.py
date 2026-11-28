from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
    SendRichMessage,
    SetMyCommands,
)
from sqlalchemy import func, select

from factories import match, rich_lines, text_of
from golli.bot import rich_view
from golli.bot.handlers.matches import recent_days, upcoming_days
from golli.db.favorites import favorite_teams
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


MAIN_MENU = ["⚽ Yaqin o'yinlar", "🏁 Oxirgi o'yinlar", "🏆 Turnirlar", "⚙️ Sozlamalar"]


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
async def test_choosing_language_saves_it_and_offers_to_pick_a_club(make_chat, db, i18n, code):
    chat = make_chat()
    await chat.send("/start")

    sent = await chat.choose_language(code)

    t = i18n.translator(code)
    assert (await get_user(db, chat.user_id)).lang == code
    # Yangi foydalanuvchi: tildan keyin sevimli klub tanlanadi; salomlashuv hali chiqmaydi.
    assert texts(sent) == [t("favorites-onboarding")]
    assert menu_buttons(sent[0]) == [
        t("competition-ucl"),
        t("competition-epl"),
        t("competition-laliga"),
        t("favorites-done"),
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


async def test_start_without_favorites_offers_to_pick_a_club(make_chat, i18n):
    chat = make_chat()
    await chat.choose_language("ru")

    sent = await chat.send("/start")

    t = i18n.translator("ru")
    assert texts(sent) == [t("favorites-onboarding")]
    assert menu_buttons(sent[0])[-1] == t("favorites-done")


async def test_start_with_favorites_goes_straight_to_main_menu(chat, db, i18n):
    await store(db, match("m1", datetime(2026, 11, 28, 15, 0, tzinfo=ZoneInfo("UTC"))))
    await chat.send("⭐ Sevimli klublar")
    await chat.send(i18n.translate("uz", "competition-epl"))
    await chat.send("Arsenal")

    sent = await chat.send("/start")

    assert texts(sent) == [i18n.translate("uz", "start-welcome", name="Ali")]
    assert menu_buttons(sent[0]) == MAIN_MENU


async def test_new_user_picks_a_club_right_after_choosing_language(make_chat, db, i18n):
    await store(db, match("m1", datetime(2026, 11, 28, 15, 0, tzinfo=ZoneInfo("UTC"))))
    chat = make_chat()
    await chat.send("/start")
    await chat.choose_language("uz")

    [clubs] = await chat.send(i18n.translate("uz", "competition-epl"))
    # "Tayyor" ro'yxat boshida alohida qatorda, "Orqaga" (ligalarga) — eng pastda.
    rows = [[button.text for button in row] for row in clubs.reply_markup.keyboard]
    assert rows[0] == ["✅ Tayyor"]
    assert rows[-1] == ["⬅️ Orqaga"]
    [added] = await chat.send("Arsenal")
    assert added.text == "✅ Qo'shildi: Arsenal"
    assert menu_buttons(added)[0] == "✅ Tayyor"

    # "Tayyor" bosilgach salomlashuv va asosiy menyu chiqadi.
    [greeting] = await chat.send("✅ Tayyor")
    assert greeting.text == i18n.translate("uz", "start-welcome", name="Ali")
    assert greeting.text.startswith("Assalomu alaykum, Ali!")
    assert menu_buttons(greeting) == MAIN_MENU
    async with db() as session:
        assert [team.name for team in await favorite_teams(session, chat.user_id)] == ["Arsenal"]


async def test_new_user_may_finish_without_picking_a_club(make_chat, i18n):
    chat = make_chat()
    await chat.choose_language("uz")

    [greeting] = await chat.send("✅ Tayyor")

    assert greeting.text.startswith("Assalomu alaykum, Ali!")
    assert menu_buttons(greeting) == MAIN_MENU
    # Tanishuv tugadi: endi sevimli klublar faqat Sozlamalar orqali ochiladi.
    [unknown] = await chat.send(i18n.translate("uz", "competition-epl"))
    assert unknown.text == i18n.translate("uz", "unknown-message")


async def test_back_from_clubs_during_first_start_returns_to_leagues(make_chat, db, i18n):
    await store(db, match("m1", datetime(2026, 11, 28, 15, 0, tzinfo=ZoneInfo("UTC"))))
    chat = make_chat()
    await chat.choose_language("uz")
    await chat.send(i18n.translate("uz", "competition-epl"))
    await chat.send("Arsenal")

    [leagues] = await chat.send("⬅️ Orqaga")

    assert "• Arsenal" in leagues.text
    assert menu_buttons(leagues)[-1] == "✅ Tayyor"


async def test_changing_language_later_does_not_restart_club_picking(chat, i18n):
    sent = await chat.choose_language("en")

    t = i18n.translator("en")
    assert texts(sent) == [t("start-welcome", name="Ali")]
    assert menu_buttons(sent[0]) == [
        t("menu-matches"),
        t("menu-recent"),
        t("menu-tournaments"),
        t("menu-settings"),
    ]


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

    sent = await chat.send("✅ Tayyor")

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
    [no_upcoming] = await chat.send(t("menu-matches"))
    assert no_upcoming.text.endswith(t("matches-none-upcoming"))
    [no_recent] = await chat.send(t("menu-recent"))
    assert no_recent.text.endswith(t("matches-none-recent"))


async def test_unknown_text_gets_hint_with_menu(chat, i18n):
    sent = await chat.send("salom")

    assert texts(sent) == [i18n.translate("uz", "unknown-message")]
    assert menu_buttons(sent[0]) == MAIN_MENU


# --- Sozlamalar


async def test_settings_hold_favourites_and_language(chat, i18n):
    [settings] = await chat.send("⚙️ Sozlamalar")

    assert settings.text == "⚙️ <b>Sozlamalar</b>\n\nKerakli bo'limni tanlang 👇"
    assert [[button.text for button in row] for row in settings.reply_markup.keyboard] == [
        ["⭐ Sevimli klublar", "🌐 Til"],
        ["⬅️ Orqaga"],
    ]

    [favorites] = await chat.send("⭐ Sevimli klublar")
    assert favorites.text.startswith("⭐ <b>Sevimli klublar</b>")
    assert is_language_prompt(await chat.send("🌐 Til"))


async def test_keyboards_can_be_hidden_by_the_user(chat, db, i18n):
    await store(db, match("m1", datetime(2026, 11, 28, 15, 0, tzinfo=ZoneInfo("UTC"))))
    screens = [
        (await chat.send("/help"))[0],
        (await chat.send("⚙️ Sozlamalar"))[0],
        (await chat.send("⭐ Sevimli klublar"))[0],
        (await chat.send(i18n.translate("uz", "competition-epl")))[0],
    ]

    # "Doim ochiq" rejimi yoqilmagan: Telegram yozish maydonida klaviaturani yashirish
    # tugmasini ko'rsatadi.
    assert [screen.reply_markup.is_persistent for screen in screens] == [None] * 4
    assert all(screen.reply_markup.resize_keyboard for screen in screens)


async def test_back_from_settings_returns_to_main_menu(chat):
    await chat.send("⚙️ Sozlamalar")

    [sent] = await chat.send("⬅️ Orqaga")

    assert sent.text == "🏠 Asosiy menyu"
    assert menu_buttons(sent) == MAIN_MENU


@pytest.mark.parametrize("code", ["ru", "en"])
async def test_settings_buttons_work_in_other_languages(make_chat, i18n, code):
    chat = make_chat()
    await chat.choose_language(code)
    t = i18n.translator(code)

    [settings] = await chat.send(t("menu-settings"))
    assert menu_buttons(settings) == [t("menu-favorites"), t("menu-language"), t("menu-back")]
    [back] = await chat.send(t("menu-back"))
    assert back.text == t("menu-main")


# --- Yaqin o'yinlar (jadvalli xabar; satrlar factories.rich_lines ko'rinishida)


async def store(db, *items):
    async with db.begin() as session:
        await upsert_matches(session, "fake", items)


def pair(home: str, away: str) -> str:
    """Boshlanmagan o'yin jadval qatorining klublar qismi."""
    return f"⚽ {home} | – | ⚽ {away}"


def finished(external_id: str, kickoff_at, home: str, away: str, **kwargs):
    return match(
        external_id, kickoff_at, home, away, status=MatchStatus.FINISHED, score=(2, 1), **kwargs
    )


def day_titles(text: str) -> int:
    return sum(line.startswith("### ") for line in text.split("\n"))


async def test_matches_today_are_shown_with_the_next_match_day(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        match("m0", start + timedelta(hours=23, minutes=50), "Arsenal", "Chelsea"),
        # Ertaga o'yin yo'q; keyingi o'yin kuni — indinga.
        match("m2", start + timedelta(days=2, hours=12), "Liverpool", "Everton"),
        match("m3", start + timedelta(days=5, hours=12), "Arsenal", "Manchester City"),
    )

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    assert isinstance(sent, SendRichMessage)
    lines = text_of(sent).split("\n")
    assert lines[0].startswith("### ⚽ Bugun, ")
    assert any(pair("Arsenal", "Chelsi") in line for line in lines)
    assert day_titles(text_of(sent)) == 2
    assert any(pair("Liverpul", "Everton") in line for line in lines)
    assert "Man Siti" not in text_of(sent)


async def test_finished_match_moves_from_upcoming_to_recent(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        finished(
            "done", start + timedelta(minutes=1), "Real Madrid", "Barcelona", competition="laliga"
        ),
        match("next", start + timedelta(hours=23, minutes=50), "Arsenal", "Chelsea"),
    )

    [upcoming] = await chat.send("⚽ Yaqin o'yinlar")
    [recent] = await chat.send("🏁 Oxirgi o'yinlar")

    # Tugagan o'yin "Yaqin o'yinlar"da yo'q, "Oxirgi o'yinlar"da bor.
    assert "Real Madrid" not in text_of(upcoming)
    assert pair("Arsenal", "Chelsi") in text_of(upcoming)
    assert "⚽ Real Madrid | 2:1 | ⚽ Barselona" in text_of(recent).split("\n")
    assert "Arsenal" not in text_of(recent)


async def test_day_with_only_finished_matches_drops_out_of_upcoming(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        finished(
            "done", start + timedelta(minutes=1), "Real Madrid", "Barcelona", competition="laliga"
        ),
        match("m2", start + timedelta(days=2, hours=12), "Liverpool", "Everton"),
        match("m3", start + timedelta(days=3, hours=12), "Arsenal", "Manchester City"),
    )

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    # Bugun hamma o'yin tugagan: ro'yxat keyingi ikki o'yin kunidan boshlanadi.
    text = text_of(sent)
    assert "Bugun" not in text and "Real Madrid" not in text
    assert day_titles(text) == 2
    assert pair("Liverpul", "Everton") in text and pair("Arsenal", "Man Siti") in text


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

    text = text_of(sent)
    assert "Bugun" not in text
    assert pair("Real Madrid", "Barselona") in text
    assert pair("Liverpul", "Everton") in text
    assert "Man Siti" not in text
    assert text.index("Real Madrid") < text.index("Liverpul")


async def test_single_upcoming_match_day(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(db, match("m1", start + timedelta(days=2, hours=12)))

    [sent] = await chat.send("⚽ Yaqin o'yinlar")

    assert day_titles(text_of(sent)) == 1


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
    assert menu_buttons(sent) == MAIN_MENU


@pytest.mark.parametrize("button", ["⚽ Yaqin o'yinlar", "🏁 Oxirgi o'yinlar"])
async def test_plain_text_is_sent_when_telegram_rejects_the_table(chat, db, schedule, bot, button):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(
        db,
        finished("old", start - timedelta(hours=12), "Arsenal", "Everton"),
        match("m1", start + timedelta(days=1, hours=12), "Liverpool", "Everton"),
    )
    bot.session.method_failures[SendRichMessage] = lambda method: TelegramBadRequest(
        method=method, message="Bad Request: rich messages are not supported"
    )

    sent = await chat.send(button)

    # Jadvalli xabar o'tmadi: o'sha ro'yxat oddiy matnda, menyu bilan birga yuboriladi.
    rejected, plain = sent
    assert isinstance(rejected, SendRichMessage) and isinstance(plain, SendMessage)
    assert "<code>" in plain.text and "Everton" in plain.text
    assert menu_buttons(plain) == MAIN_MENU


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
    # Eski xabar joyida tahrirlanadi, shuning uchun bu yerda ro'yxat oddiy matnda.
    assert "<code>Liverpul</code> ⚽ <code>Everton</code>" in edit.text
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

    text = text_of(sent)
    assert day_titles(text) == 2
    # Hisob klublar orasida; soat ustuni yo'q, chunki hamma o'yin tugagan.
    assert "⚽ Real Madrid | 2:1 | ⚽ Barselona" in text.split("\n")
    assert "⚽ Liverpul | 2:1 | ⚽ Everton" in text.split("\n")
    assert text.index("Real Madrid") < text.index("Liverpul")
    assert "Man Siti" not in text
    # Natijalar ro'yxatida soat yo'q, demak vaqt mintaqasi haqida izoh ham yo'q.
    assert "O'zbekiston bo'yicha" not in text


async def test_nothing_recent(chat, db, schedule):
    start, _ = day_bounds(schedule.today(), schedule.tz)
    await store(db, match("next", start + timedelta(days=1, hours=12)))

    [sent] = await chat.send("🏁 Oxirgi o'yinlar")

    assert sent.text == "<b>🏁 Oxirgi o'yinlar</b>\n\nSo'nggi kunlarda o'yin bo'lmadi."


# --- Yarim tun atrofida

TASHKENT = ZoneInfo("Asia/Tashkent")


def tashkent(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TASHKENT)


async def shown_lines(days_of, schedule, i18n, names, now: datetime) -> list[str]:
    """Berilgan paytdagi ro'yxat: jadvalli xabar satrlari."""
    await schedule.rebuild(now)
    rich = rich_view.days_message(
        await days_of(schedule, now),
        today=schedule.today(now),
        now=now,
        t=i18n.translator("uz"),
        names=names,
        tz=schedule.tz,
    )
    return rich_lines(rich)


async def upcoming(schedule, i18n, names, now: datetime) -> list[str]:
    return await shown_lines(upcoming_days, schedule, i18n, names, now)


async def recent(schedule, i18n, names, now: datetime) -> list[str]:
    return await shown_lines(recent_days, schedule, i18n, names, now)


async def test_night_match_is_listed_under_its_own_date(db, schedule, i18n, names):
    await store(
        db,
        match("sat", tashkent(28, 20), "Arsenal", "Manchester City"),
        match("night", tashkent(29, 1), "Real Madrid", "Barcelona", competition="laliga"),
    )

    lines = await upcoming(schedule, i18n, names, tashkent(28, 12))

    saturday = lines.index("### ⚽ Bugun, 28-noyabr, shanba")
    sunday = lines.index("### ⚽ Ertaga, 29-noyabr, yakshanba")
    assert saturday < lines.index("20:00 | ⚽ Arsenal | – | ⚽ Man Siti") < sunday
    assert lines.index("01:00 | ⚽ Real Madrid | – | ⚽ Barselona") > sunday
    assert lines[-1] == "🕐 Vaqt — O'zbekiston bo'yicha"


async def test_match_still_in_play_after_midnight_stays_in_the_list(db, schedule, i18n, names):
    await store(
        db,
        finished("early", tashkent(28, 17), "Liverpool", "Everton"),
        match("late", tashkent(28, 23), status=MatchStatus.LIVE, score=(1, 0)),
        match("night", tashkent(29, 1), "Real Madrid", "Barcelona", competition="laliga"),
        match("monday", tashkent(30, 20), "Club Brugge KV", "Liverpool", competition="ucl"),
    )

    # Yakshanba 00:30: shanba kungi o'yin hali ketmoqda — ro'yxat kechadan boshlanadi.
    lines = await upcoming(schedule, i18n, names, tashkent(29, 0, 30))
    assert lines[0] == "### ⚽ Kecha, 28-noyabr, shanba"
    # Bitta jadvalda: tugagan o'yinda birinchi katak bo'sh, jonli o'yinda 🔴.
    # Tugagan o'yin bu ro'yxatda yo'q (u "Oxirgi o'yinlar"da), jonli o'yin esa bor.
    assert not any("Liverpul | 2:1" in line for line in lines)
    assert "⚽ Arsenal | 1:0 | ⚽ Man Siti" in [line.removeprefix("🔴 | ") for line in lines]
    assert "### ⚽ Bugun, 29-noyabr, yakshanba" in lines
    assert "🔴 O'yin ketmoqda — hisob kechikib yangilanadi" in lines
    assert not any("Bryugge" in line for line in lines)

    # O'yin tugagach ro'yxat yana bugundan boshlanadi.
    await store(db, finished("late", tashkent(28, 23), "Arsenal", "Manchester City"))
    lines = await upcoming(schedule, i18n, names, tashkent(29, 1, 30))
    assert lines[0] == "### ⚽ Bugun, 29-noyabr, yakshanba"
    assert not any("Kecha" in line for line in lines)
    assert f"20:00 | {pair('Bryugge', 'Liverpul')}" in lines


async def test_stuck_match_does_not_hold_yesterday_in_the_list(db, schedule, i18n, names):
    # Holati yangilanmay qolgan kechagi o'yin ro'yxatni ertasi kuni ham kechadan boshlatmaydi.
    await store(
        db,
        match("stuck", tashkent(28, 17), status=MatchStatus.LIVE, score=(1, 0)),
        match("sunday", tashkent(29, 19), "Liverpool", "Everton"),
    )

    lines = await upcoming(schedule, i18n, names, tashkent(29, 10))

    assert lines[0] == "### ⚽ Bugun, 29-noyabr, yakshanba"


async def test_recent_keeps_night_match_under_its_own_date(db, schedule, i18n, names):
    await store(
        db,
        finished("sat", tashkent(28, 20), "Arsenal", "Manchester City"),
        finished("night", tashkent(29, 1), "Real Madrid", "Barcelona", competition="laliga"),
    )

    lines = await recent(schedule, i18n, names, tashkent(29, 12))

    sunday = lines.index("### ⚽ Bugun, 29-noyabr, yakshanba")
    saturday = lines.index("### ⚽ Kecha, 28-noyabr, shanba")
    assert sunday < lines.index("⚽ Real Madrid | 2:1 | ⚽ Barselona") < saturday
    assert lines.index("⚽ Arsenal | 2:1 | ⚽ Man Siti") > saturday


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

    lines = await recent(schedule, i18n, names, tashkent(28, 21))

    assert lines[0] == "### ⚽ Bugun, 28-noyabr, shanba"
    assert "⚽ Liverpul | 2:1 | ⚽ Everton" in lines
    # Ko'chirilgan o'yin belgisi bilan chiqadi, belgi izohi jadval ostida.
    assert "⏸ | ⚽ Bryugge | – | ⚽ Liverpul" in lines
    assert lines[-1] == "⏸ — ko'chirilgan"
    text = "\n".join(lines)
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
