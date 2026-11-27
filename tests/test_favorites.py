from datetime import UTC, datetime

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText
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
    return [[button.text for button in row] for row in message.reply_markup.inline_keyboard]


def keyboard_data(message) -> list[str]:
    return [b.callback_data for row in message.reply_markup.inline_keyboard for b in row]


def last_edit(chat) -> EditMessageText:
    edit = chat.requests[-1]
    assert isinstance(edit, EditMessageText)
    return edit


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


# --- Bot


async def test_empty_state_offers_leagues(chat, i18n):
    [sent] = await chat.send(ROOT_BUTTON)

    assert sent.text == (
        "⭐ <b>Sevimli klublar</b>\n\n"
        "Hali klub tanlanmagan.\n\n"
        "Klub qo'shish yoki olib tashlash uchun ligani tanlang."
    )
    t = i18n.translator("uz")
    assert keyboard_rows(sent) == [
        [t("competition-ucl")],
        [t("competition-epl")],
        [t("competition-laliga")],
    ]
    assert keyboard_data(sent) == ["favl:ucl:0", "favl:epl:0", "favl:laliga:0"]


async def test_league_shows_its_clubs_sorted_in_user_language(chat, clubs, i18n):
    await chat.press("favl:epl:0")

    edit = last_edit(chat)
    assert edit.text == (
        f"<b>{i18n.translate('uz', 'competition-epl')}</b>\n\n"
        "Klubni bosib tanlang. Qayta bossangiz, olib tashlanadi."
    )
    assert keyboard_rows(edit) == [
        ["Arsenal", "Everton"],
        ["Liverpul", "Manchester Siti"],
        ["⬅️ Ligalar"],
    ]
    assert keyboard_data(edit)[-1] == "fav"


async def test_club_names_follow_language(make_chat, clubs):
    chat = make_chat()
    await chat.choose_language("ru")

    await chat.press("favl:epl:0")

    assert keyboard_rows(last_edit(chat))[:2] == [
        ["Арсенал", "Ливерпуль"],
        ["Манчестер Сити", "Эвертон"],
    ]


async def test_tapping_a_club_selects_and_tapping_again_removes(chat, db, clubs):
    arsenal = await team_id(db, "Arsenal")

    await chat.press(f"favt:epl:0:{arsenal}")

    answer = chat.requests[0]
    assert isinstance(answer, AnswerCallbackQuery)
    assert answer.text == "✅ Qo'shildi: Arsenal"
    assert keyboard_rows(last_edit(chat))[0] == ["✅ Arsenal", "Everton"]
    assert await favorite_names(db, chat.user_id) == ["Arsenal"]

    await chat.press(f"favt:epl:0:{arsenal}")

    assert chat.requests[0].text == "❌ Olib tashlandi: Arsenal"
    assert keyboard_rows(last_edit(chat))[0] == ["Arsenal", "Everton"]
    assert await favorite_names(db, chat.user_id) == []


async def test_club_logos_are_shown_on_buttons_and_in_the_chosen_list(chat, db, clubs):
    async with db.begin() as session:
        await session.execute(update(Team).where(Team.name == "Arsenal").values(emoji_id="5001"))
    arsenal = await team_id(db, "Arsenal")

    await chat.press(f"favt:epl:0:{arsenal}")

    buttons = [button for row in last_edit(chat).reply_markup.inline_keyboard for button in row]
    icons = {button.text: button.icon_custom_emoji_id for button in buttons}
    assert icons["✅ Arsenal"] == "5001"
    # Emojisi hali yaratilmagan klub tugmasi logotipsiz qoladi.
    assert icons["Everton"] is None

    [root] = await chat.send(ROOT_BUTTON)
    assert '• <tg-emoji emoji-id="5001">⚽</tg-emoji> Arsenal' in root.text


async def test_several_clubs_from_different_leagues(chat, db, clubs):
    await chat.press(f"favt:epl:0:{await team_id(db, 'Liverpool')}")
    await chat.press(f"favt:laliga:0:{await team_id(db, 'Real Madrid')}")
    await chat.press(f"favt:laliga:0:{await team_id(db, 'Barcelona')}")

    assert await favorite_names(db, chat.user_id) == ["Liverpool", "Real Madrid", "Barcelona"]

    expected = (
        "⭐ <b>Sevimli klublar</b>\n\n"
        "Tanlangan klublar:\n"
        "• Liverpul\n"
        "• Real Madrid\n"
        "• Barselona\n\n"
        "Klub qo'shish yoki olib tashlash uchun ligani tanlang."
    )
    [sent] = await chat.send(ROOT_BUTTON)
    assert sent.text == expected
    # "Ligalar" tugmasi ham shu sahifaga qaytaradi.
    await chat.press("fav")
    assert last_edit(chat).text == expected


async def test_favorites_belong_to_each_user_separately(make_chat, db, clubs):
    arsenal = await team_id(db, "Arsenal")
    first, second = make_chat(user_id=1), make_chat(user_id=2)
    for chat in (first, second):
        await chat.choose_language("uz")

    await first.press(f"favt:epl:0:{arsenal}")
    await second.press("favl:epl:0")

    assert await favorite_names(db, 1) == ["Arsenal"]
    assert await favorite_names(db, 2) == []
    assert keyboard_rows(last_edit(second))[0] == ["Arsenal", "Everton"]


async def test_long_list_is_split_into_pages(chat, db):
    # 22 ta klub: birinchi sahifada 20 ta, ikkinchisida 2 ta.
    await store(
        db,
        *[
            match(
                f"s{i}",
                KICKOFF,
                f"Klub {2 * i:02}",
                f"Klub {2 * i + 1:02}",
                competition="ucl",
                round="League Stage - 1",
            )
            for i in range(11)
        ],
    )

    await chat.press("favl:ucl:0")
    first = last_edit(chat)
    assert first.text.split("\n")[0].endswith(" · 1/2")
    assert sum(data.startswith("favt:ucl:0:") for data in keyboard_data(first)) == 20
    assert keyboard_rows(first)[-2:] == [["▶️"], ["⬅️ Ligalar"]]
    assert "favl:ucl:1" in keyboard_data(first)

    await chat.press("favl:ucl:1")
    second = last_edit(chat)
    assert second.text.split("\n")[0].endswith(" · 2/2")
    assert keyboard_rows(second) == [["Klub 20", "Klub 21"], ["◀️"], ["⬅️ Ligalar"]]

    # Mavjud bo'lmagan sahifa oxirgi sahifaga keltiriladi.
    await chat.press("favl:ucl:9")
    assert keyboard_rows(last_edit(chat))[0] == ["Klub 20", "Klub 21"]


async def test_selection_on_second_page_stays_on_that_page(chat, db):
    await store(
        db,
        *[
            match(
                f"s{i}",
                KICKOFF,
                f"Klub {2 * i:02}",
                f"Klub {2 * i + 1:02}",
                competition="ucl",
                round="League Stage - 1",
            )
            for i in range(11)
        ],
    )

    await chat.press(f"favt:ucl:1:{await team_id(db, 'Klub 21')}")

    assert keyboard_rows(last_edit(chat))[0] == ["Klub 20", "✅ Klub 21"]


async def test_league_without_data(chat):
    await chat.press("favl:laliga:0")

    edit = last_edit(chat)
    assert edit.text.endswith("Bu liga klublari hali yuklanmagan.")
    assert keyboard_rows(edit) == [["⬅️ Ligalar"]]


@pytest.mark.parametrize("data", ["favl:nba:0", "favt:nba:0:1", "favt:epl:0:999999"])
async def test_unknown_league_or_club_is_ignored(chat, db, clubs, data):
    await chat.press(data)

    assert [type(request) for request in chat.requests] == [AnswerCallbackQuery]
    assert await favorite_names(db, chat.user_id) == []
