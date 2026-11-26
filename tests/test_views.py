from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from golli.bot.views import day_navigation, render_days, render_no_upcoming
from golli.providers.base import MatchStatus
from golli.services.schedule import DayMatch

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
    day_match("laliga", at(29, 1), "Real Madrid", "Barcelona"),
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
            "22:45  Bryugge — Liverpul",
            "",
            f"<b>{t('competition-epl')}</b>",
            "✅ Everton <b>0:2</b> Liverpul",
            "🔴 Arsenal <b>1:0</b> Manchester Siti",
            "🔴 Fulxem — Bornmut",
            "",
            "<b>🇪🇸 La Liga</b>",
            "⏸ Xetafe — Valensiya · ko'chirilgan",
            "🌙 01:00  Real Madrid — Barselona",
            "",
            "🌙 Yarim tundan keyin (29-noyabr)",
            "",
            "🕐 Vaqt — Toshkent bo'yicha",
            "🔴 O'yin ketmoqda — hisob kechikib yangilanadi",
        ]
    )


@pytest.mark.parametrize(
    ("locale", "title", "line"),
    [
        ("ru", "⚽ <b>Сегодня, 28 ноября, суббота</b>", "✅ Эвертон <b>0:2</b> Ливерпуль"),
        ("en", "⚽ <b>Today, Saturday, 28 November</b>", "✅ Everton <b>0:2</b> Liverpool"),
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

    assert "23:00  Arsenal — Manchester Siti" in text
    assert text.endswith("🕐 Vaqt — Toshkent bo'yicha")


@pytest.mark.parametrize(
    ("locale", "note"),
    [
        ("uz", "🌙 Yarim tundan keyin (29-noyabr)"),
        ("ru", "🌙 После полуночи (29 ноября)"),
        ("en", "🌙 After midnight (29 November)"),
    ],
)
def test_after_midnight_kickoff_is_marked_with_next_date(i18n, names, locale, note):
    night = [day_match("laliga", at(29, 1), "Real Madrid", "Barcelona")]

    lines = render(night, i18n, names, locale).split("\n")

    assert lines[3].startswith("🌙 01:00  ")
    assert lines[5] == note


def test_no_night_note_once_the_night_match_has_started(i18n, names):
    night = [day_match("laliga", at(29, 1), "Real Madrid", "Barcelona", MatchStatus.LIVE, (0, 0))]

    text = render(night, i18n, names, now=at(29, 1, 30))

    assert "🌙" not in text


def test_penalty_shootout_is_shown(i18n, names):
    final = [
        day_match("ucl", at(28, 1), "Real Madrid", "Arsenal", MatchStatus.FINISHED, (1, 1), (4, 3))
    ]

    assert "✅ Real Madrid <b>1:1</b> Arsenal (pen. 4:3)" in render(final, i18n, names)


@pytest.mark.parametrize(
    ("status", "line"),
    [
        (MatchStatus.SUSPENDED, "⏸ Arsenal — Chelsi · to'xtatilgan"),
        (MatchStatus.CANCELLED, "❌ Arsenal — Chelsi · bekor qilingan"),
    ],
)
def test_interrupted_matches(i18n, names, status, line):
    assert line in render([day_match("epl", at(28, 20), "Arsenal", "Chelsea", status)], i18n, names)


def test_unknown_team_keeps_provider_name_and_is_escaped(i18n, names):
    text = render([day_match("ucl", at(28, 23), "Tom & Jerry <FC>", "Viking")], i18n, names)

    assert "23:00  Tom &amp; Jerry &lt;FC&gt; — Viking" in text


# --- Bir nechta kun bitta xabarda


def test_two_days_in_one_message(i18n, names):
    saturday = [
        day_match("epl", at(28, 22, 30), "Ipswich", "Aston Villa"),
        day_match("laliga", at(29, 1), "Real Madrid", "Alavés"),
    ]
    sunday = [day_match("epl", at(29, 21, 30), "Arsenal", "Manchester City")]

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
            "22:30  Ipsvich — Aston Villa",
            "",
            "<b>🇪🇸 La Liga</b>",
            "🌙 01:00  Real Madrid — Alaves",
            "",
            "🌙 Yarim tundan keyin (29-noyabr)",
            "",
            "⚽ <b>Ertaga, 29-noyabr, yakshanba</b>",
            "",
            f"<b>{epl}</b>",
            "21:30  Arsenal — Manchester Siti",
            "",
            "🕐 Vaqt — Toshkent bo'yicha",
        ]
    )


def test_no_upcoming_matches_message(i18n):
    assert render_no_upcoming(i18n.translator("uz")) == (
        "<b>⚽ Yaqin o'yinlar</b>\n\nYaqin kunlarda o'yin yo'q."
    )


# --- Kunlar orasida o'tish

MATCH_DAYS = [date(2026, 11, 26), TODAY, date(2026, 11, 29), date(2026, 12, 5)]


def buttons(markup) -> list[tuple[str, str]]:
    return [(button.text, button.callback_data) for row in markup.inline_keyboard for button in row]


def navigation(first, last, i18n, *, back_to_upcoming, match_days=MATCH_DAYS):
    return day_navigation(
        first, last, match_days, i18n.translator("uz"), back_to_upcoming=back_to_upcoming
    )


def test_navigation_under_upcoming_list_goes_around_shown_days(i18n):
    # Ro'yxatda 28- va 29-noyabr ko'rsatilgan: tugmalar ulardan oldingi va keyingi o'yin kuniga.
    markup = navigation(TODAY, date(2026, 11, 29), i18n, back_to_upcoming=False)

    assert buttons(markup) == [
        ("◀️ Pay 26.11", "day:2026-11-26"),
        ("Shan 05.12 ▶️", "day:2026-12-05"),
    ]


def test_navigation_under_single_day_offers_way_back(i18n):
    day = date(2026, 11, 29)
    markup = navigation(day, day, i18n, back_to_upcoming=True)

    assert buttons(markup) == [
        ("◀️ Shan 28.11", "day:2026-11-28"),
        ("⚽ Yaqin o'yinlar", "upcoming"),
        ("Shan 05.12 ▶️", "day:2026-12-05"),
    ]


def test_navigation_skips_days_without_matches(i18n):
    # 27-noyabrda o'yin yo'q: undan orqaga 26-ga, oldinga 28-ga o'tiladi.
    day = date(2026, 11, 27)
    markup = navigation(day, day, i18n, back_to_upcoming=False)

    assert [data for _, data in buttons(markup)] == ["day:2026-11-26", "day:2026-11-28"]


def test_navigation_at_the_edges(i18n):
    first, last = MATCH_DAYS[0], MATCH_DAYS[-1]

    assert [
        data for _, data in buttons(navigation(first, first, i18n, back_to_upcoming=False))
    ] == ["day:2026-11-28"]
    assert [data for _, data in buttons(navigation(last, last, i18n, back_to_upcoming=False))] == [
        "day:2026-11-29"
    ]


def test_no_navigation_when_there_is_nowhere_to_go(i18n):
    assert navigation(TODAY, TODAY, i18n, back_to_upcoming=False, match_days=[TODAY]) is None
