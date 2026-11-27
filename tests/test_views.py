import tomllib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from golli.bot.views import render_days, render_no_recent, render_no_upcoming
from golli.providers.base import MatchStatus
from golli.services.schedule import DayMatch
from golli.services.team_names import TEAM_NAMES_FILE

TASHKENT = ZoneInfo("Asia/Tashkent")
TODAY = date(2026, 11, 28)  # shanba
NOW = datetime(2026, 11, 28, 21, 0, tzinfo=TASHKENT)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TASHKENT)


def day_match(
    competition: str,
    kickoff_at: datetime,
    home: str,
    away: str,
    status: MatchStatus = MatchStatus.SCHEDULED,
    score: tuple[int, int] | None = None,
    penalties: tuple[int, int] | None = None,
) -> DayMatch:
    return DayMatch(
        id=1,
        competition=competition,
        kickoff_at=kickoff_at,
        status=status,
        minute=None,
        home_id=1,
        home=home,
        away_id=2,
        away=away,
        home_score=score[0] if score else None,
        away_score=score[1] if score else None,
        home_penalties=penalties[0] if penalties else None,
        away_penalties=penalties[1] if penalties else None,
    )


MATCHES = [
    day_match("epl", at(28, 17, 30), "Everton", "Liverpool", MatchStatus.FINISHED, (0, 2)),
    day_match("epl", at(28, 20), "Arsenal", "Manchester City", MatchStatus.LIVE, (1, 0)),
    # Boshlanish vaqti o'tgan, holati hali olinmagan.
    day_match("epl", at(28, 20, 30), "Fulham", "Bournemouth"),
    day_match("ucl", at(28, 22, 45), "Club Brugge KV", "Liverpool"),
    day_match("laliga", at(28, 23), "Getafe", "Valencia", MatchStatus.POSTPONED),
    day_match("laliga", at(28, 23, 30), "Real Madrid", "Barcelona"),
]


def render(matches, i18n, names, locale="uz", day=TODAY, now=NOW) -> str:
    return render_days(
        [(day, matches)],
        today=TODAY,
        now=now,
        t=i18n.translator(locale),
        names=names,
        tz=TASHKENT,
    )


def test_full_day_in_uzbek(i18n, names):
    t = i18n.translator("uz")

    assert render(MATCHES, i18n, names) == "\n".join(
        [
            "⚽ <b>Bugun, 28-noyabr, shanba</b>",
            "",
            "<b>🏆 Chempionlar ligasi</b>",
            "22:45 Bryugge – Liverpul",
            "",
            f"<b>{t('competition-epl')}</b>",
            "Everton <b>0:2</b> Liverpul",
            "🔴 Arsenal <b>1:0</b> Man Siti",
            "🔴 Fulxem – Bornmut",
            "",
            "<b>🇪🇸 La Liga</b>",
            "⏸ Xetafe – Valensiya · ko'chirilgan",
            "23:30 Real Madrid – Barselona",
            "",
            "🕐 Vaqt — Toshkent bo'yicha",
            "🔴 O'yin ketmoqda — hisob kechikib yangilanadi",
        ]
    )


@pytest.mark.parametrize(
    ("locale", "title", "line"),
    [
        ("ru", "⚽ <b>Сегодня, 28 ноября, суббота</b>", "Эвертон <b>0:2</b> Ливерпуль"),
        ("en", "⚽ <b>Today, Saturday, 28 November</b>", "Everton <b>0:2</b> Liverpool"),
    ],
)
def test_other_languages(i18n, names, locale, title, line):
    lines = render(MATCHES, i18n, names, locale).split("\n")

    assert lines[0] == title
    assert line in lines


@pytest.mark.parametrize(
    ("day", "title"),
    [
        (TODAY + timedelta(days=1), "⚽ <b>Ertaga, 29-noyabr, yakshanba</b>"),
        (TODAY - timedelta(days=1), "⚽ <b>Kecha, 27-noyabr, juma</b>"),
        (TODAY + timedelta(days=7), "⚽ <b>5-dekabr, shanba</b>"),
    ],
)
def test_titles_of_other_days(i18n, names, day, title):
    assert render([], i18n, names, day=day).split("\n")[0] == title


def test_day_without_matches(i18n, names):
    assert render([], i18n, names) == "⚽ <b>Bugun, 28-noyabr, shanba</b>\n\nBu kuni o'yin yo'q."


def test_no_live_note_when_nothing_is_in_play(i18n, names):
    upcoming = [day_match("epl", at(28, 23), "Arsenal", "Manchester City")]

    text = render(upcoming, i18n, names)

    assert "23:00 Arsenal – Man Siti" in text
    assert text.endswith("🕐 Vaqt — Toshkent bo'yicha")


def test_after_midnight_kickoff_is_an_ordinary_match_of_its_own_date(i18n, names):
    night = [day_match("laliga", at(29, 1), "Real Madrid", "Barcelona")]

    text = render(night, i18n, names, day=date(2026, 11, 29))

    assert text == "\n".join(
        [
            "⚽ <b>Ertaga, 29-noyabr, yakshanba</b>",
            "",
            "<b>🇪🇸 La Liga</b>",
            "01:00 Real Madrid – Barselona",
            "",
            "🕐 Vaqt — Toshkent bo'yicha",
        ]
    )


def test_penalty_shootout_is_shown(i18n, names):
    final = [
        day_match("ucl", at(28, 1), "Real Madrid", "Arsenal", MatchStatus.FINISHED, (1, 1), (4, 3))
    ]

    assert "Real Madrid <b>1:1</b> Arsenal (pen. 4:3)" in render(final, i18n, names)


@pytest.mark.parametrize(
    ("status", "line"),
    [
        (MatchStatus.SUSPENDED, "⏸ Arsenal – Chelsi · to'xtatilgan"),
        (MatchStatus.CANCELLED, "❌ Arsenal – Chelsi · bekor qilingan"),
    ],
)
def test_interrupted_matches(i18n, names, status, line):
    assert line in render([day_match("epl", at(28, 20), "Arsenal", "Chelsea", status)], i18n, names)


def test_unknown_team_keeps_provider_name_and_is_escaped(i18n, names):
    text = render([day_match("ucl", at(28, 23), "Tom & Jerry <FC>", "Viking")], i18n, names)

    assert "23:00 Tom &amp; Jerry &lt;FC&gt; – Viking" in text


# --- Bir nechta kun bitta xabarda


def test_two_days_in_one_message(i18n, names):
    saturday = [day_match("epl", at(28, 22, 30), "Ipswich", "Aston Villa")]
    sunday = [
        day_match("laliga", at(29, 1), "Real Madrid", "Alavés"),
        day_match("epl", at(29, 21, 30), "Arsenal", "Manchester City"),
    ]

    text = render_days(
        [(TODAY, saturday), (TODAY + timedelta(days=1), sunday)],
        today=TODAY,
        now=at(28, 12),
        t=i18n.translator("uz"),
        names=names,
        tz=TASHKENT,
    )

    epl = i18n.translate("uz", "competition-epl")
    assert text == "\n".join(
        [
            "⚽ <b>Bugun, 28-noyabr, shanba</b>",
            "",
            f"<b>{epl}</b>",
            "22:30 Ipsvich – Aston Villa",
            "",
            "⚽ <b>Ertaga, 29-noyabr, yakshanba</b>",
            "",
            f"<b>{epl}</b>",
            "21:30 Arsenal – Man Siti",
            "",
            "<b>🇪🇸 La Liga</b>",
            "01:00 Real Madrid – Alaves",
            "",
            "🕐 Vaqt — Toshkent bo'yicha",
        ]
    )


def test_no_upcoming_matches_message(i18n):
    assert render_no_upcoming(i18n.translator("uz")) == (
        "<b>⚽ Yaqin o'yinlar</b>\n\nYaqin kunlarda o'yin yo'q."
    )


def test_no_recent_matches_message(i18n):
    assert render_no_recent(i18n.translator("uz")) == (
        "<b>🏁 Oxirgi o'yinlar</b>\n\nSo'nggi kunlarda o'yin bo'lmadi."
    )


def test_time_zone_note_only_when_a_kickoff_time_is_shown(i18n, names):
    results = [
        day_match("epl", at(28, 17, 30), "Everton", "Liverpool", MatchStatus.FINISHED, (0, 2)),
        day_match("laliga", at(28, 18), "Getafe", "Valencia", MatchStatus.POSTPONED),
    ]

    # Faqat natijalar: soat ko'rsatilmagan, demak vaqt mintaqasi haqida izoh ham yo'q.
    assert render(results, i18n, names).split("\n")[-1] == "⏸ Xetafe – Valensiya · ko'chirilgan"

    in_play = [day_match("epl", at(28, 20), "Arsenal", "Manchester City", MatchStatus.LIVE, (1, 0))]
    assert render(in_play, i18n, names).split("\n")[-2:] == [
        "",
        "🔴 O'yin ketmoqda — hisob kechikib yangilanadi",
    ]


# --- Klub logotiplari (maxsus emoji)


def logo(emoji_id: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">⚽</tg-emoji>'


def with_logos(match: DayMatch, home: str | None, away: str | None) -> DayMatch:
    return match.model_copy(update={"home_emoji": home, "away_emoji": away})


def test_club_logo_stands_before_the_club_name(i18n, names):
    matches = [
        with_logos(
            day_match("epl", at(28, 17, 30), "Everton", "Liverpool", MatchStatus.FINISHED, (0, 2)),
            "11",
            "12",
        ),
        with_logos(
            day_match("epl", at(28, 20), "Arsenal", "Manchester City", MatchStatus.LIVE, (1, 0)),
            "13",
            "14",
        ),
        with_logos(day_match("laliga", at(28, 23), "Real Madrid", "Barcelona"), "15", "16"),
    ]

    lines = render(matches, i18n, names).split("\n")

    assert f"{logo('11')} Everton <b>0:2</b> {logo('12')} Liverpul" in lines
    assert f"🔴 {logo('13')} Arsenal <b>1:0</b> {logo('14')} Man Siti" in lines
    assert f"23:00 {logo('15')} Real Madrid – {logo('16')} Barselona" in lines


def test_club_without_logo_is_shown_by_name_only(i18n, names):
    # Emoji hali yaratilmagan klub: nomi o'zi qoladi, yonidagi klub logotipi bilan.
    half = with_logos(day_match("laliga", at(28, 23), "Real Madrid", "Barcelona"), None, "16")

    assert f"23:00 Real Madrid – {logo('16')} Barselona" in render([half], i18n, names)


# --- Qisqa nomlar: o'yin qatori telefonda bitta satrga sig'ishi uchun


@pytest.mark.parametrize(
    ("locale", "line"),
    [
        ("uz", "23:00 MYU – Brentford"),
        ("ru", "23:00 МЮ – Брентфорд"),
        ("en", "23:00 Man Utd – Brentford"),
    ],
)
def test_long_club_names_are_shortened_in_match_lines(i18n, names, locale, line):
    long = [day_match("epl", at(28, 23), "Manchester United", "Brentford")]

    assert line in render(long, i18n, names, locale).split("\n")


def test_short_name_falls_back_to_full_name(names):
    assert names.short("Manchester United", "uz") == "MYU"
    assert names.get("Manchester United", "uz") == "Manchester Yunayted"
    # Qisqasi yozilmagan klub va tarjimasi umuman yo'q klub.
    assert names.short("Arsenal", "ru") == "Арсенал"
    assert names.short("Viking", "uz") == "Viking"


def test_short_names_are_really_shorter():
    with TEAM_NAMES_FILE.open("rb") as file:
        clubs = tomllib.load(file)

    for name, fields in clubs.items():
        for key, short in fields.items():
            if key.endswith("_short"):
                full = fields.get(key.removesuffix("_short"), name)
                assert len(short) < len(full), (name, key)
