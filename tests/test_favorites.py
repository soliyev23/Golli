from datetime import UTC, datetime

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup
from sqlalchemy import select, update

from factories import match
from golli.db.favorites import competition_teams, favorite_teams, toggle_favorite
from golli.db.matches import upsert_matches
from golli.db.models import Team
from golli.db.users import get_or_create_user

KICKOFF = datetime(2026, 11, 29, 16, 30, tzinfo=UTC)
ROOT_BUTTON = "⭐ Sevimli klublar"


async def store(db, *items):
    async with db.begin() as session:
        await upsert_matches(session, "fake", items)


async def team_id(db, name: str) -> int:
    async with db() as session:
        return await session.scalar(select(Team.id).where(Team.name == name))


async def favorite_names(db, user_id: int) -> list[str]:
    async with db() as session:
        return [team.name for team in await favorite_teams(session, user_id)]


@pytest.fixture
async def clubs(db) -> None:
    """Ikki APL o'yini va bitta La Liga o'yini: jami oltita klub."""
    await store(
        db,
        match("e1", KICKOFF, "Arsenal", "Manchester City"),
        match("e2", KICKOFF, "Liverpool", "Everton"),
        match("l1", KICKOFF, "Real Madrid", "Barcelona", competition="laliga"),
    )


def keyboard_rows(message) -> list[list[str]]:
    return [[button.text for button in row] for row in message.reply_markup.keyboard]


# --- Baza


async def test_competition_teams(db, clubs):
    async with db() as session:
        epl = await competition_teams(session, "epl")
        laliga = await competition_teams(session, "laliga")
        ucl = await competition_teams(session, "ucl")

    assert {team.name for team in epl} == {"Arsenal", "Manchester City", "Liverpool", "Everton"}
    assert {team.name for team in laliga} == {"Real Madrid", "Barcelona"}
    assert ucl == []


async def test_ucl_list_has_only_league_stage_clubs(db):
    await store(
        db,
        match(
            "q1",
            KICKOFF,
            "Kairat Almaty",
            "Omonia Nicosia",
            competition="ucl",
            round="2nd Qualifying Round",
        ),
        match("q2", KICKOFF, "Celje", "Slovan Bratislava", competition="ucl", round="Play-offs"),
        match(
            "s1",
            KICKOFF,
            "Club Brugge KV",
            "Liverpool",
            competition="ucl",
            round="League Stage - 5",
        ),
        match(
            "s2",
            KICKOFF,
            "Slovan Bratislava",
            "Real Madrid",
            competition="ucl",
            round="League Stage - 6",
        ),
    )

    async with db() as session:
        teams = await competition_teams(session, "ucl")

    # Slovan saralashdan o'tgan — ro'yxatda bor; Kairat, Omonia va Celje yo'q.
    assert {team.name for team in teams} == {
        "Club Brugge KV",
        "Liverpool",
        "Slovan Bratislava",
        "Real Madrid",
    }


async def test_only_latest_season_clubs_are_listed(db):
    await store(
        db,
        match("old", KICKOFF.replace(year=2025), "Everton", "Liverpool", season=2025),
        match("new", KICKOFF, "Arsenal", "Liverpool"),
    )

    async with db() as session:
        teams = await competition_teams(session, "epl")

    assert {team.name for team in teams} == {"Arsenal", "Liverpool"}


async def test_toggle_adds_then_removes(db, clubs):
    arsenal = await team_id(db, "Arsenal")
    async with db.begin() as session:
        await get_or_create_user(session, 1)

    async with db.begin() as session:
        team, selected = await toggle_favorite(session, 1, arsenal)
    assert (team.name, selected) == ("Arsenal", True)
    assert await favorite_names(db, 1) == ["Arsenal"]

    async with db.begin() as session:
        team, selected = await toggle_favorite(session, 1, arsenal)
    assert (team.name, selected) == ("Arsenal", False)
    assert await favorite_names(db, 1) == []


async def test_toggle_unknown_team(db):
    async with db.begin() as session:
        await get_or_create_user(session, 1)
        assert await toggle_favorite(session, 1, 999_999) is None


# --- Bot: pastki klaviatura


BACK = "⬅️ Orqaga"


async def open_league(chat, i18n, competition: str = "epl", locale: str = "uz"):
    [sent] = await chat.send(i18n.translate(locale, f"competition-{competition}"))
    return sent


async def test_empty_state_offers_leagues(chat, i18n):
    [sent] = await chat.send(ROOT_BUTTON)

    assert sent.text == (
        "⭐ <b>Sevimli klublar</b>\n\n"
        "Hali klub tanlanmagan.\n\n"
        "Klub qo'shish yoki olib tashlash uchun ligani tanlang."
    )
    t = i18n.translator("uz")
    # Ligalar xabar ostida emas, pastki klaviaturada.
    assert keyboard_rows(sent) == [
        [t("competition-ucl")],
        [t("competition-epl"), t("competition-laliga")],
        [BACK],
    ]


async def test_league_shows_its_clubs_sorted_in_user_language(chat, clubs, i18n):
    sent = await open_league(chat, i18n)

    assert sent.text == (
        f"<b>{i18n.translate('uz', 'competition-epl')}</b>\n\n"
        "Klubni bosib tanlang. Qayta bossangiz, olib tashlanadi."
    )
    assert keyboard_rows(sent) == [
        ["Arsenal", "Everton"],
        ["Liverpul", "Manchester Siti"],
        [BACK],
    ]


async def test_club_names_follow_language(make_chat, clubs, i18n):
    chat = make_chat()
    await chat.choose_language("ru")

    sent = await open_league(chat, i18n, locale="ru")

    assert keyboard_rows(sent) == [
        ["Арсенал", "Ливерпуль"],
        ["Манчестер Сити", "Эвертон"],
        ["⬅️ Назад"],
    ]


async def test_tapping_a_club_selects_and_tapping_again_removes(chat, db, clubs, i18n):
    await open_league(chat, i18n)

    [added] = await chat.send("Arsenal")

    assert added.text == "✅ Qo'shildi: Arsenal"
    # Javob bilan klaviatura yangilanadi: tanlangan klub belgilangan.
    assert keyboard_rows(added)[0] == ["✅ Arsenal", "Everton"]
    assert await favorite_names(db, chat.user_id) == ["Arsenal"]

    [removed] = await chat.send("✅ Arsenal")

    assert removed.text == "❌ Olib tashlandi: Arsenal"
    assert keyboard_rows(removed)[0] == ["Arsenal", "Everton"]
    assert await favorite_names(db, chat.user_id) == []


async def test_club_logos_are_shown_on_buttons_and_in_replies(chat, db, clubs, i18n):
    async with db.begin() as session:
        await session.execute(update(Team).where(Team.name == "Arsenal").values(emoji_id="5001"))

    sent = await open_league(chat, i18n)
    icons = {b.text: b.icon_custom_emoji_id for row in sent.reply_markup.keyboard for b in row}
    assert icons["Arsenal"] == "5001"
    # Emojisi hali yaratilmagan klub tugmasi logotipsiz qoladi.
    assert icons["Everton"] is None

    [added] = await chat.send("Arsenal")
    assert added.text == '✅ Qo\'shildi: <tg-emoji emoji-id="5001">⚽</tg-emoji> Arsenal'

    [root] = await chat.send(ROOT_BUTTON)
    assert '• <tg-emoji emoji-id="5001">⚽</tg-emoji> Arsenal' in root.text


async def test_several_clubs_from_different_leagues(chat, db, clubs, i18n):
    await chat.send(ROOT_BUTTON)
    await open_league(chat, i18n)
    await chat.send("Arsenal")
    await chat.send("Liverpul")
    # "Orqaga" klublardan ligalar ro'yxatiga qaytaradi.
    [leagues] = await chat.send(BACK)
    assert "• Arsenal\n• Liverpul" in leagues.text
    assert keyboard_rows(leagues)[0] == [i18n.translate("uz", "competition-ucl")]

    await open_league(chat, i18n, "laliga")
    await chat.send("Barselona")

    assert await favorite_names(db, chat.user_id) == ["Arsenal", "Liverpool", "Barcelona"]


async def test_back_goes_one_step_at_a_time_to_settings_and_main_menu(chat, clubs, i18n):
    await chat.send("⚙️ Sozlamalar")
    await chat.send(ROOT_BUTTON)
    await open_league(chat, i18n)

    [leagues] = await chat.send(BACK)
    assert leagues.text.startswith("⭐ <b>Sevimli klublar</b>")

    [settings] = await chat.send(BACK)
    assert settings.text.startswith("⚙️ <b>Sozlamalar</b>")
    assert keyboard_rows(settings) == [["⭐ Sevimli klublar", "🌐 Til"], [BACK]]

    [main] = await chat.send(BACK)
    assert main.text == "🏠 Asosiy menyu"
    assert keyboard_rows(main) == [["⚽ Yaqin o'yinlar", "🏁 Oxirgi o'yinlar"], ["⚙️ Sozlamalar"]]


async def test_back_after_first_start_shows_the_choice_and_opens_main_menu(make_chat, clubs, i18n):
    chat = make_chat()
    await chat.choose_language("uz")  # yangi foydalanuvchi: klub tanlash taklif qilingan

    await open_league(chat, i18n)
    await chat.send("Arsenal")
    await chat.send(BACK)
    [summary] = await chat.send(BACK)

    assert summary.text == (
        "⭐ <b>Sevimli klublaringiz:</b>\n• Arsenal\n\nUlarning o'yinlari haqida eslatib turaman."
    )
    assert keyboard_rows(summary) == [["⚽ Yaqin o'yinlar", "🏁 Oxirgi o'yinlar"], ["⚙️ Sozlamalar"]]


async def test_skipping_the_choice_after_first_start(make_chat, i18n):
    chat = make_chat()
    await chat.choose_language("uz")

    [summary] = await chat.send(BACK)

    assert summary.text.startswith("Klub tanlanmadi.")
    assert keyboard_rows(summary)[-1] == ["⚙️ Sozlamalar"]


async def test_favorites_belong_to_each_user_separately(make_chat, db, clubs, i18n):
    first, second = make_chat(user_id=1), make_chat(user_id=2)
    await first.choose_language("uz")
    await second.choose_language("uz")

    await open_league(first, i18n)
    await first.send("Arsenal")
    # Ikkinchi foydalanuvchi boshqa ligada: har kimning holati o'ziniki.
    await open_league(second, i18n, "laliga")
    [reply] = await second.send("Real Madrid")

    assert reply.text == "✅ Qo'shildi: Real Madrid"
    assert await favorite_names(db, 1) == ["Arsenal"]
    assert await favorite_names(db, 2) == ["Real Madrid"]


async def test_whole_league_fits_one_scrollable_keyboard(chat, db, i18n):
    # Chempionlar ligasi asosiy bosqichi: 36 ta klub, sahifalarsiz.
    await store(
        db,
        *[
            match(
                f"u{index}",
                KICKOFF,
                f"Klub {index:02d}",
                f"Klub {index + 18:02d}",
                competition="ucl",
                round="League Stage - 1",
            )
            for index in range(1, 19)
        ],
    )

    sent = await open_league(chat, i18n, "ucl")

    rows = keyboard_rows(sent)
    assert len(rows) == 19
    assert rows[0] == ["Klub 01", "Klub 02"]
    assert rows[17] == ["Klub 35", "Klub 36"]

    [reply] = await chat.send("Klub 36")
    assert keyboard_rows(reply)[17] == ["Klub 35", "✅ Klub 36"]


async def test_league_without_data(chat, i18n):
    sent = await open_league(chat, i18n, "ucl")

    assert sent.text.endswith("Bu liga klublari hali yuklanmagan.")
    assert keyboard_rows(sent) == [[BACK]]


async def test_unknown_text_in_club_list_keeps_the_list(chat, db, clubs, i18n):
    await open_league(chat, i18n)

    [reply] = await chat.send("Barselona")  # bu ligada bunday klub yo'q

    assert reply.text == "Pastdagi tugmalardan tanlang 👇"
    assert keyboard_rows(reply)[0] == ["Arsenal", "Everton"]
    assert await favorite_names(db, chat.user_id) == []


async def test_club_name_outside_the_list_is_not_a_choice(chat, db, clubs, i18n):
    # Klublar ro'yxati ochilmagan: klub nomi oddiy tushunarsiz xabar.
    [reply] = await chat.send("Arsenal")
    assert reply.text == i18n.translate("uz", "unknown-message")

    # Ligalar ro'yxatida ham klub tanlanmaydi: liga tanlash so'raladi.
    await chat.send(ROOT_BUTTON)
    [reply] = await chat.send("Arsenal")
    assert reply.text == "Pastdagi tugmalardan tanlang 👇"
    assert keyboard_rows(reply)[-1] == [BACK]

    # Bo'limdan chiqilgach ham shunday.
    await chat.send(BACK)
    [reply] = await chat.send("Arsenal")
    assert reply.text == i18n.translate("uz", "unknown-message")
    assert await favorite_names(db, chat.user_id) == []


@pytest.mark.parametrize("command", ["/start", "/help"])
async def test_command_closes_the_club_list(chat, db, clubs, i18n, command):
    await open_league(chat, i18n)

    await chat.send(command)
    await chat.send("Arsenal")

    assert await favorite_names(db, chat.user_id) == []


@pytest.mark.parametrize("data", ["fav", "favl:epl:0", "favt:epl:0:1"])
async def test_buttons_left_in_old_messages_are_retired(chat, db, clubs, data):
    assert await chat.press(data) == []

    answer, edit = chat.requests
    assert isinstance(answer, AnswerCallbackQuery)
    assert answer.text == "Bu tugmalar eskirgan. Pastdagi menyudan foydalaning."
    assert isinstance(edit, EditMessageReplyMarkup) and edit.reply_markup is None
    assert await favorite_names(db, chat.user_id) == []
