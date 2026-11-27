"""Eslatma xabarlarining matni."""

from datetime import date, datetime, tzinfo
from itertools import groupby
from math import ceil

from golli.bot.views import VERSUS, club_label, render_days, score_line
from golli.i18n import Translator
from golli.services.days import local_date
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
    return "\n".join(
        [
            title,
            "",
            f"<b>{home}{VERSUS}{away}</b>",
            f"{t(f'competition-{match.competition}')} · {kickoff}",
        ]
    )


def render_result(match: DayMatch, t: Translator, names: TeamNames) -> str:
    return "\n".join(
        [
            t("notify-result-title"),
            "",
            score_line(match, t, names),
            t(f"competition-{match.competition}"),
        ]
    )


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
