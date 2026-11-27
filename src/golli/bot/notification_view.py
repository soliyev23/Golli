"""Eslatma xabarlarining matni."""

from datetime import date, datetime, tzinfo
from html import escape
from itertools import groupby
from math import ceil

from golli.bot.views import VERSUS, club_label, league_title, render_days, score_line
from golli.i18n import Translator
from golli.services.days import local_date
from golli.services.knockout import advancing_side, aggregate_of, stage_of
from golli.services.schedule import DayMatch
from golli.services.team_names import TeamNames

# Xabar o'z vaqtida ketsa "1 soat qoldi" deyiladi; kechiksa, qolgan daqiqalar yoziladi.
HOUR_THRESHOLD_MINUTES = 50


def render_pre_match(
    match: DayMatch, now: datetime, t: Translator, names: TeamNames, tz: tzinfo
) -> str:
    minutes = ceil((match.kickoff_at - now).total_seconds() / 60)
    if minutes >= HOUR_THRESHOLD_MINUTES:
        title = t("notify-pre-hour")
    else:
        title = t("notify-pre-minutes", minutes=minutes)
    home = club_label(match.home, match.home_emoji, t, names, short=True)
    away = club_label(match.away, match.away_emoji, t, names, short=True)
    kickoff = match.kickoff_at.astimezone(tz).strftime("%H:%M")
    lines = [
        title,
        "",
        f"<b>{home}{VERSUS}{away}</b>",
        f"{_league(match, t)} · {kickoff}",
    ]
    if match.first_leg_home is not None and match.first_leg_away is not None:
        # Javob o'yini: birinchi o'yin o'sha paytdagi mezbon tartibida eslatiladi.
        first_leg = _score_text(
            match.away, match.first_leg_away, match.first_leg_home, match.home, t, names
        )
        lines.append(t("notify-first-leg", score=first_leg))
    return "\n".join(lines)


def render_result(match: DayMatch, t: Translator, names: TeamNames) -> str:
    lines = [
        t("notify-result-title"),
        "",
        score_line(match, t, names),
        _league(match, t),
    ]
    if total := aggregate_of(match):
        total_text = _score_text(match.home, total[0], total[1], match.away, t, names)
        lines.append(t("notify-aggregate", score=total_text))
    if winner := advancing_side(match):
        # Pley-off: kim keyingi bosqichga chiqqani (finalda — g'olib) alohida satrda.
        team = match.home if winner == "home" else match.away
        emoji = match.home_emoji if winner == "home" else match.away_emoji
        key = "notify-champion" if stage_of(match) == "final" else "notify-advances"
        lines.append(t(key, team=club_label(team, emoji, t, names, short=True)))
    return "\n".join(lines)


def _league(match: DayMatch, t: Translator) -> str:
    """Liga nomi, pley-off o'yinida bosqichi bilan."""
    return league_title(match.competition, stage_of(match), t)


def _score_text(
    home: str, home_goals: int, away_goals: int, away: str, t: Translator, names: TeamNames
) -> str:
    """ "Benfika 2:1 Real Madrid" — logotipsiz, qisqa nomlar bilan."""
    home_name = escape(names.short(home, t.locale), quote=False)
    away_name = escape(names.short(away, t.locale), quote=False)
    return f"{home_name} {home_goals}:{away_goals} {away_name}"


def render_morning(
    today: date,
    matches: list[DayMatch],
    now: datetime,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
) -> str:
    """Sevimli klublarning yaqin o'yinlari (boshlanish tartibida), har biri o'z sanasi ostida.

    Yarim tundan keyin boshlanadigan o'yin ertangi sana sarlavhasi bilan chiqadi.
    """
    days = morning_days(matches, tz)
    schedule = render_days(days, today=today, now=now, t=t, names=names, tz=tz)
    return f"{t('notify-morning-title')}\n\n{schedule}"


def morning_days(matches: list[DayMatch], tz: tzinfo) -> list[tuple[date, list[DayMatch]]]:
    """Boshlanish tartibidagi o'yinlar — taqvim sanalari bo'yicha guruhlangan."""
    return [
        (day, list(group))
        for day, group in groupby(matches, key=lambda match: local_date(match.kickoff_at, tz))
    ]
