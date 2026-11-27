from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendRichMessage
from sqlalchemy import update

from factories import rich_lines, standing
from golli.bot.standings_view import render_standings
from golli.db.models import Team
from golli.db.standings import StandingRow, replace_standings

TASHKENT = ZoneInfo("Asia/Tashkent")
UPDATED = datetime(2026, 11, 28, 10, 0, tzinfo=TASHKENT)
MENU_BUTTON = "🏆 Turnirlar"
BACK = "⬅️ Orqaga"
ARSENAL_LOGO = '<tg-emoji emoji-id="5001">⚽</tg-emoji>'


def keyboard_rows(message) -> list[list[str]]:
    return [[button.text for button in row] for row in message.reply_markup.keyboard]


def league(i18n, competition: str, locale: str = "uz") -> str:
    return i18n.translate(locale, f"competition-{competition}")


@pytest.fixture
async def epl_table(db) -> None:
    async with db.begin() as session:
        await replace_standings(
            session,
            "fake",
            "epl",
            2026,
            [
                standing(1, "Arsenal", 25, goals=(18, 4)),
                standing(2, "Manchester City", 22, goals=(20, 9)),
                standing(3, "Everton", 9, goals=(8, 15)),
            ],
            UPDATED,
        )
        await session.execute(update(Team).where(Team.name == "Arsenal").values(emoji_id="5001"))


# --- Bo'lim


async def test_tournaments_button_offers_the_three_leagues(chat, i18n):
    [sent] = await chat.send(MENU_BUTTON)

    assert sent.text == "🏆 <b>Turnirlar</b>\n\nJadvalini ko'rish uchun turnirni tanlang 👇"
    assert keyboard_rows(sent) == [
        [league(i18n, "ucl")],
        [league(i18n, "epl"), league(i18n, "laliga")],
        [BACK],
    ]


async def test_choosing_a_league_shows_its_table(chat, epl_table, i18n):
    await chat.send(MENU_BUTTON)

    [sent] = await chat.send(league(i18n, "epl"))

    # Haqiqiy jadval (jadvalli xabar): sarlavha qatori, keyin har klub — o'rin, logotip va nom,
    # o'yinlar, to'plar farqi, ochko.
    assert isinstance(sent, SendRichMessage)
    assert rich_lines(sent.rich_message) == [
        f"### {league(i18n, 'epl')}",
        "# | Klub | O' | +/- | O",
        "1 | <5001> Arsenal | 10 | +14 | 25",
        "2 | ⚽ Man Siti | 10 | +11 | 22",
        "3 | ⚽ Everton | 10 | -7 | 9",
        "🕐 Yangilangan: 28-noyabr, 10:00",
    ]
    table = sent.rich_message.blocks[1]
    assert [cell.is_header for cell in table.cells[0]] == [True] * 5
    assert [cell.align for cell in table.cells[1]] == ["right", "left", "right", "right", "right"]
    # Ligalar klaviaturasi joyida qoladi: boshqa turnirga o'tish mumkin.
    assert keyboard_rows(sent)[-1] == [BACK]

    [other] = await chat.send(league(i18n, "laliga"))
    assert other.text.endswith("Jadval hali yuklanmagan. Birozdan keyin urinib ko'ring.")


async def test_plain_table_is_sent_when_telegram_rejects_the_rich_one(chat, epl_table, i18n, bot):
    await chat.send(MENU_BUTTON)
    bot.session.method_failures[SendRichMessage] = lambda method: TelegramBadRequest(
        method=method, message="Bad Request: rich messages are not supported"
    )

    rejected, plain = await chat.send(league(i18n, "epl"))

    assert isinstance(rejected, SendRichMessage)
    # Zaxira ko'rinish: ustunlar teng enli shriftda tekislangan oddiy matn.
    assert f"<code> 1</code> {ARSENAL_LOGO} <code>Arsenal  10 +14 25</code>" in plain.text
    assert keyboard_rows(plain)[-1] == [BACK]


async def test_back_returns_to_main_menu(chat):
    await chat.send(MENU_BUTTON)

    [sent] = await chat.send(BACK)

    assert sent.text == "🏠 Asosiy menyu"
    assert keyboard_rows(sent) == [
        ["⚽ Yaqin o'yinlar", "🏁 Oxirgi o'yinlar"],
        ["🏆 Turnirlar", "⚙️ Sozlamalar"],
    ]


async def test_league_button_means_table_here_and_clubs_in_favourites(chat, epl_table, i18n):
    await chat.send(MENU_BUTTON)
    [table] = await chat.send(league(i18n, "epl"))
    assert "1 | <5001> Arsenal | 10 | +14 | 25" in rich_lines(table.rich_message)

    await chat.send(BACK)
    await chat.send("⭐ Sevimli klublar")
    [clubs] = await chat.send(league(i18n, "epl"))
    assert clubs.text.endswith("Bu liga klublari hali yuklanmagan.")


async def test_league_name_outside_any_section_is_not_understood(chat, epl_table, i18n):
    [sent] = await chat.send(league(i18n, "epl"))

    assert sent.text == i18n.translate("uz", "unknown-message")


async def test_other_text_in_the_section_asks_to_choose(chat, i18n):
    await chat.send(MENU_BUTTON)

    [sent] = await chat.send("jadval")

    assert sent.text == "Pastdagi tugmalardan tanlang 👇"
    assert keyboard_rows(sent)[0] == [league(i18n, "ucl")]


@pytest.mark.parametrize(
    ("code", "header", "updated"),
    [
        ("ru", "# | Клуб | И | +/- | О", "🕐 Обновлено: 28 ноября, 10:00"),
        ("en", "# | Club | P | +/- | Pt", "🕐 Updated: 28 November, 10:00"),
    ],
)
async def test_table_in_other_languages(make_chat, epl_table, i18n, code, header, updated):
    chat = make_chat()
    await chat.choose_language(code)
    t = i18n.translator(code)

    await chat.send(t("menu-tournaments"))
    [sent] = await chat.send(t("competition-epl"))

    lines = rich_lines(sent.rich_message)
    assert lines[1] == header
    assert lines[-1] == updated


# --- Ko'rinish


def row(position: int, team: str, points: int, group: str | None = None) -> StandingRow:
    return StandingRow(
        position=position,
        team=team,
        team_emoji=None,
        played=5,
        wins=points // 3,
        draws=points % 3,
        losses=5 - points // 3 - points % 3,
        goals_for=10,
        goals_against=10,
        points=points,
        group=group,
    )


def test_long_club_names_are_short_and_zero_difference_has_no_sign(i18n, names):
    text = render_standings(
        "epl", [row(1, "Manchester United", 12)], UPDATED, i18n.translator("uz"), names, TASHKENT
    )

    assert "<code> 1</code> ⚽ <code>MYU   5   0 12</code>" in text.split("\n")


def test_columns_line_up_whatever_the_name_and_number_lengths(i18n, names):
    rows = [
        row(1, "Arsenal", 12),
        row(9, "Aston Villa", 7),
        row(10, "Tom & Jerry <FC>", 6),
        row(20, "Everton", 0),
    ]

    lines = render_standings("epl", rows, UPDATED, i18n.translator("uz"), names, TASHKENT).split(
        "\n"
    )[2:7]

    # Har qator: o'rin (2 belgi), logotip, qolgan ustunlar.
    positions = [line.split("</code>")[0].removeprefix("<code>") for line in lines]
    assert positions == [" #", " 1", " 9", "10", "20"]
    cells = [line.rsplit("<code>", 1)[1].removesuffix("</code>") for line in lines]
    assert cells == [
        "Klub             O' +/-  O",
        "Arsenal           5   0 12",
        "Aston Villa       5   0  7",
        "Tom &amp; Jerry &lt;FC&gt;  5   0  6",
        "Everton           5   0  0",
    ]
    # Ekranda (HTML belgilari ochilgach) barcha qatorlar bir xil uzunlikda.
    shown = [cell.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") for cell in cells]
    assert {len(cell) for cell in shown} == {26}


def test_groups_are_shown_under_their_names(i18n, names):
    rows = [
        row(1, "Arsenal", 9, "A guruhi"),
        row(2, "Everton", 3, "A guruhi"),
        row(1, "Liverpool", 7, "B guruhi"),
    ]

    text = render_standings("ucl", rows, UPDATED, i18n.translator("uz"), names, TASHKENT)

    assert text.split("\n")[2:9] == [
        "<code> #</code> 📊 <code>Klub     O' +/-  O</code>",
        "<b>A guruhi</b>",
        "<code> 1</code> ⚽ <code>Arsenal   5   0  9</code>",
        "<code> 2</code> ⚽ <code>Everton   5   0  3</code>",
        "",
        "<b>B guruhi</b>",
        "<code> 1</code> ⚽ <code>Liverpul  5   0  7</code>",
    ]


def test_big_table_stays_within_telegram_formatting_limit(i18n, names):
    # Chempionlar ligasi: 36 qator. Har qatorda logotip va ikkita <code> bo'lagi bo'lsa,
    # 100 talik limitdan oshadi — shuning uchun qo'shni bo'laklar ulanadi.
    rows = [
        StandingRow(
            position=position,
            team=f"Klub {position:02d}",
            team_emoji=str(5000 + position),
            played=5,
            wins=1,
            draws=1,
            losses=3,
            goals_for=5,
            goals_against=8,
            points=4,
            group=None,
        )
        for position in range(1, 37)
    ]

    text = render_standings("ucl", rows, UPDATED, i18n.translator("uz"), names, TASHKENT)

    entities = sum(text.count(tag) for tag in ("<code>", "<tg-emoji", "<b>", "<i>"))
    assert entities <= 100
    assert text.count("<tg-emoji") == 36
    # Matnning o'zi (formatlashsiz) o'zgarmagan: har qatorda o'rin, logotip, klub.
    lines = text.split("\n")
    assert lines[3].endswith("</tg-emoji> <code>Klub 01  5  -3  4")
    assert lines[4].startswith(" 2</code> <tg-emoji")
    assert lines[38].endswith("<code>Klub 36  5  -3  4</code>")
