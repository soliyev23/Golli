"""Pley-off bosqichi: bosqich nomi, ikki o'yin yig'indisi va keyingi bosqichga chiqqan klub."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from aiogram.types import RichTextBold

from factories import match, rich_lines
from golli.bot import rich_view
from golli.bot.notification_view import render_pre_match, render_result
from golli.bot.standings_view import render_knockout
from golli.bot.views import render_days
from golli.competitions import knockout_stage
from golli.db.matches import upsert_matches
from golli.db.models import Match
from golli.providers.base import MatchStatus
from golli.services.knockout import advancing_side, aggregate_of, load_ties, stage_of
from golli.services.schedule import DayMatch, load_matches

TASHKENT = ZoneInfo("Asia/Tashkent")
FIRST_LEG = datetime(2027, 2, 17, 1, 0, tzinfo=TASHKENT)
SECOND_LEG = datetime(2027, 2, 24, 1, 0, tzinfo=TASHKENT)
PLAYOFF = "Round of 32"  # provayder pley-off bosqichini shunday ataydi
FINISHED = MatchStatus.FINISHED


def tie(*, second_status=MatchStatus.SCHEDULED, second_score=None, penalties=None, stage=PLAYOFF):
    """Liverpul — Real Madrid 2:1 (birinchi o'yin) va Real Madrid — Liverpul (javob o'yini)."""
    return [
        match(
            "first",
            FIRST_LEG,
            "Liverpool",
            "Real Madrid",
            competition="ucl",
            round=stage,
            status=FINISHED,
            score=(2, 1),
        ),
        match(
            "second",
            SECOND_LEG,
            "Real Madrid",
            "Liverpool",
            competition="ucl",
            round=stage,
            status=second_status,
            score=second_score,
            penalties=penalties,
        ),
    ]


async def loaded(db, *items) -> list[DayMatch]:
    async with db.begin() as session:
        await upsert_matches(session, "fake", items)
    async with db() as session:
        return await load_matches(session, Match.id.is_not(None))


def layout(i18n, names, now, locale="uz"):
    return {
        "today": now.date(),
        "now": now,
        "t": i18n.translator(locale),
        "names": names,
        "tz": TASHKENT,
    }


# --- Bosqichlar


@pytest.mark.parametrize(
    ("round_name", "stage"),
    [
        ("Round of 32", "playoff"),
        ("Round of 16", "round16"),
        ("Quarter-finals", "quarter"),
        ("Semi-finals", "semi"),
        ("Final", "final"),
        ("League Stage - 6", None),
        ("Play-offs", None),  # avgustdagi saralash pley-offi — bu boshqa bosqich
        (None, None),
    ],
)
def test_provider_round_names_map_to_stages(round_name, stage):
    assert knockout_stage("ucl", round_name) == stage


def test_other_leagues_have_no_knockout_stages():
    assert knockout_stage("epl", "Round of 16") is None


# --- Birinchi o'yin va yig'indi


async def test_second_leg_knows_the_first_leg_score(db):
    first, second = await loaded(db, *tie())

    # Birinchi o'yinda Real mehmon bo'lib 1 ta, Liverpul 2 ta gol urgan; javob o'yinida Real mezbon.
    assert (second.first_leg_home, second.first_leg_away) == (1, 2)
    assert aggregate_of(second) == (1, 2)
    assert (first.first_leg_home, first.first_leg_away) == (None, None)
    assert aggregate_of(first) is None
    assert stage_of(first) == stage_of(second) == "playoff"


async def test_league_matches_between_the_same_clubs_have_no_aggregate(db):
    home = match("h", FIRST_LEG, "Arsenal", "Everton", status=FINISHED, score=(2, 0))
    away = match("a", SECOND_LEG, "Everton", "Arsenal")

    matches = await loaded(db, home, away)

    assert [aggregate_of(m) for m in matches] == [None, None]


async def test_unfinished_first_leg_gives_no_aggregate(db):
    first = match("first", FIRST_LEG, "Liverpool", "Real Madrid", competition="ucl", round=PLAYOFF)
    second = match(
        "second", SECOND_LEG, "Real Madrid", "Liverpool", competition="ucl", round=PLAYOFF
    )

    _, loaded_second = await loaded(db, first, second)

    assert aggregate_of(loaded_second) is None


@pytest.mark.parametrize(
    ("score", "penalties", "total", "winner"),
    [
        ((3, 0), None, (4, 2), "home"),  # Real yig'indida ustun
        ((1, 1), None, (2, 3), "away"),  # Liverpul birinchi o'yin hisobiga o'tadi
        ((1, 0), (4, 3), (2, 2), "home"),  # yig'indi teng — penaltilar
        ((1, 0), (2, 4), (2, 2), "away"),
        ((1, 0), None, (2, 2), None),  # teng, penaltilar haqida ma'lumot yo'q
    ],
)
async def test_who_goes_through_after_the_second_leg(db, score, penalties, total, winner):
    first, second = await loaded(
        db, *tie(second_status=FINISHED, second_score=score, penalties=penalties)
    )

    assert aggregate_of(second) == total
    assert advancing_side(second) == winner
    # Birinchi o'yin hech kimni keyingi bosqichga chiqarmaydi.
    assert advancing_side(first) is None


async def test_final_is_a_single_match(db):
    [final] = await loaded(
        db,
        match(
            "f",
            SECOND_LEG,
            "Paris Saint Germain",
            "Arsenal",
            competition="ucl",
            round="Final",
            status=FINISHED,
            score=(1, 1),
            penalties=(4, 3),
        ),
    )

    assert stage_of(final) == "final"
    assert aggregate_of(final) is None
    assert advancing_side(final) == "home"


# --- Ro'yxatlar


async def test_list_shows_stage_and_aggregate_before_the_second_leg(db, i18n, names):
    _, second = await loaded(db, *tie())
    now = SECOND_LEG - timedelta(hours=12)

    rich = rich_view.days_message(
        [(now.date() + timedelta(days=1), [second])], **layout(i18n, names, now)
    )

    assert rich_lines(rich)[1:] == [
        "##### 🏆 Chempionlar ligasi · Pley-off",
        # Chiziqcha yonida — birinchi o'yindan keyingi yig'indi (Real 1, Liverpul 2).
        "01:00 | ⚽ Real Madrid | – (1:2) | ⚽ Liverpul",
        "🕐 Vaqt — Toshkent bo'yicha",
        "Qavs ichida — ikki o'yin yig'indisi",
    ]


async def test_list_shows_result_aggregate_penalties_and_the_winner_in_bold(db, i18n, names):
    _, second = await loaded(
        db, *tie(second_status=FINISHED, second_score=(1, 0), penalties=(4, 3))
    )
    now = SECOND_LEG + timedelta(hours=6)

    rich = rich_view.days_message([(now.date(), [second])], **layout(i18n, names, now))

    assert rich_lines(rich)[1:] == [
        "##### 🏆 Chempionlar ligasi · Pley-off",
        "⚽ Real Madrid | 1:0 (2:2) (pen. 4:3) | ⚽ Liverpul",
        "Qavs ichida — ikki o'yin yig'indisi",
    ]
    # Keyingi bosqichga chiqqan klub (penaltilarda yutgan Real) nomi qalin yozilgan.
    home, _, away = rich.blocks[2].cells[0]
    assert any(isinstance(part, RichTextBold) and part.text == "Real Madrid" for part in home.text)
    assert not any(
        isinstance(part, RichTextBold) for part in away.text if not isinstance(part, str)
    )


@pytest.mark.parametrize(
    ("locale", "title"),
    [
        ("ru", "##### 🏆 Лига чемпионов · Стыковые матчи"),
        ("en", "##### 🏆 Champions League · Play-offs"),
    ],
)
async def test_stage_names_in_other_languages(db, i18n, names, locale, title):
    _, second = await loaded(db, *tie())
    now = SECOND_LEG - timedelta(hours=12)

    rich = rich_view.days_message(
        [(now.date() + timedelta(days=1), [second])], **layout(i18n, names, now, locale)
    )

    assert rich_lines(rich)[1] == title


async def test_first_leg_and_league_matches_look_as_before(db, i18n, names):
    first, _ = await loaded(db, *tie())
    now = FIRST_LEG + timedelta(hours=6)

    lines = rich_lines(rich_view.days_message([(now.date(), [first])], **layout(i18n, names, now)))

    assert lines[1:] == [
        "##### 🏆 Chempionlar ligasi · Pley-off",
        "⚽ Liverpul | 2:1 | ⚽ Real Madrid",
    ]


async def test_plain_text_fallback_also_shows_stage_and_aggregate(db, i18n, names):
    _, second = await loaded(db, *tie(second_status=FINISHED, second_score=(3, 0)))
    now = SECOND_LEG + timedelta(hours=6)

    text = render_days([(now.date(), [second])], **layout(i18n, names, now))

    assert "<b>🏆 Chempionlar ligasi · Pley-off</b>" in text
    assert "⚽ <code>Real Madrid 3:0</code> ⚽ <code>Liverpul</code> (4:2)" in text
    assert text.endswith("Qavs ichida — ikki o'yin yig'indisi")


# --- Eslatmalar


async def test_pre_match_reminder_mentions_stage_and_first_leg(db, i18n, names):
    _, second = await loaded(db, *tie())
    now = SECOND_LEG - timedelta(hours=1)

    text = render_pre_match(second, now, i18n.translator("uz"), names, TASHKENT)

    assert text.split("\n")[2:] == [
        "<b>Real Madrid – Liverpul</b>",
        "🏆 Chempionlar ligasi · Pley-off · 01:00",
        "Birinchi o'yin: Liverpul 2:1 Real Madrid",
    ]


async def test_result_reminder_tells_the_aggregate_and_who_goes_through(db, i18n, names):
    _, second = await loaded(db, *tie(second_status=FINISHED, second_score=(1, 1)))

    text = render_result(second, i18n.translator("uz"), names)

    assert text.split("\n")[2:] == [
        "Real Madrid <b>1:1</b> Liverpul",
        "🏆 Chempionlar ligasi · Pley-off",
        "Ikki o'yin yig'indisi: Real Madrid 2:3 Liverpul",
        "➡️ Keyingi bosqichga: Liverpul",
    ]


async def test_first_leg_result_has_no_aggregate_lines(db, i18n, names):
    first, _ = await loaded(db, *tie())

    text = render_result(first, i18n.translator("uz"), names)

    assert text.split("\n")[2:] == [
        "Liverpul <b>2:1</b> Real Madrid",
        "🏆 Chempionlar ligasi · Pley-off",
    ]


async def test_final_result_names_the_winner(db, i18n, names):
    [final] = await loaded(
        db,
        match(
            "f",
            SECOND_LEG,
            "Paris Saint Germain",
            "Arsenal",
            competition="ucl",
            round="Final",
            status=FINISHED,
            score=(1, 1),
            penalties=(4, 3),
        ),
    )

    text = render_result(final, i18n.translator("uz"), names)

    assert text.split("\n")[2:] == [
        "PSJ <b>1:1</b> Arsenal (pen. 4:3)",
        "🏆 Chempionlar ligasi · Final",
        "🏆 G'olib: PSJ",
    ]


# --- Juftliklar jadvali («Turnirlar» → Chempionlar ligasi → Pley-off)


def knockout_match(external_id, kickoff, home, away, round_name, score=None, penalties=None):
    return match(
        external_id,
        kickoff,
        home,
        away,
        competition="ucl",
        round=round_name,
        status=FINISHED if score else MatchStatus.SCHEDULED,
        score=score,
        penalties=penalties,
    )


async def ties_of(db, *items):
    async with db.begin() as session:
        await upsert_matches(session, "fake", items)
    async with db() as session:
        return await load_ties(session, "ucl")


async def test_matches_are_grouped_into_ties(db):
    ties = await ties_of(
        db,
        *tie(second_status=FINISHED, second_score=(3, 0)),
        knockout_match("a1", FIRST_LEG, "Arsenal", "Everton", PLAYOFF, (1, 1)),
        # Liga bosqichi o'yini juftlik emas.
        match(
            "league", FIRST_LEG, "Arsenal", "Liverpool", competition="ucl", round="League Stage - 8"
        ),
    )

    assert [(t.stage, t.first.home, t.first.away, t.second is not None) for t in ties] == [
        ("playoff", "Liverpool", "Real Madrid", True),
        ("playoff", "Arsenal", "Everton", False),
    ]


async def test_knockout_table_lists_ties_latest_stage_first(db, i18n, names):
    ties = await ties_of(
        db,
        *tie(second_status=FINISHED, second_score=(3, 0)),
        knockout_match(
            "r1", SECOND_LEG + timedelta(days=14), "Real Madrid", "Arsenal", "Round of 16", (1, 0)
        ),
        knockout_match(
            "r2", SECOND_LEG + timedelta(days=21), "Arsenal", "Real Madrid", "Round of 16"
        ),
        knockout_match("f", SECOND_LEG + timedelta(days=90), "Arsenal", "Everton", "Final"),
    )

    rich = rich_view.knockout_message("ucl", ties, i18n.translator("uz"), names, TASHKENT)

    assert rich_lines(rich) == [
        "### 🏆 Chempionlar ligasi",
        # Final — bitta o'yin: hali o'ynalmagan, o'rnida sanasi.
        "##### Final",
        "⚽ Arsenal | 25.05 | ⚽ Everton",
        # 1/8 final: birinchi o'yin o'ynalgan, javob o'yini sanasi bilan.
        "##### 1/8 final",
        " | 1 | 2 | Jami | ",
        "⚽ Real Madrid | 1:0 | 17.03 | 1:0 | ⚽ Arsenal",
        # Pley-off: javob o'yini hisobi ham juftlik tartibida (Liverpul gollari oldin).
        "##### Pley-off",
        " | 1 | 2 | Jami | ",
        "⚽ Liverpul | 2:1 | 0:3 | 2:4 | ⚽ Real Madrid",
    ]
    # Keyingi bosqichga chiqqan klub (Real Madrid, o'ngda) nomi qalin.
    left, *_, right = rich.blocks[-1].cells[1]
    assert any(isinstance(part, RichTextBold) for part in right.text)
    assert not any(isinstance(part, RichTextBold) for part in left.text)


async def test_tie_decided_on_penalties(db, i18n, names):
    ties = await ties_of(db, *tie(second_status=FINISHED, second_score=(1, 0), penalties=(4, 3)))

    rich = rich_view.knockout_message("ucl", ties, i18n.translator("uz"), names, TASHKENT)

    # Penaltilar ham juftlik tartibida: javob o'yinida Real mezbon edi (4), jadvalda u o'ngda.
    assert rich_lines(rich)[-1] == "⚽ Liverpul | 2:1 | 0:1 | 2:2 (pen. 3:4) | ⚽ Real Madrid"
    assert any(isinstance(part, RichTextBold) for part in rich.blocks[-1].cells[1][-1].text)


async def test_plain_text_knockout_fallback(db, i18n, names):
    ties = await ties_of(db, *tie(second_status=FINISHED, second_score=(3, 0)))

    text = render_knockout("ucl", ties, i18n.translator("uz"), names, TASHKENT)

    assert text.split("\n") == [
        "<b>🏆 Chempionlar ligasi</b>",
        "",
        "<b>Pley-off</b>",
        "Liverpul – Real Madrid: 2:1, 0:3",
    ]
