"""Eslatma xabarlarining matni."""

from datetime import date, datetime, tzinfo
from html import escape
from math import ceil

from golli.bot.views import match_groups, score_line
from golli.i18n import Translator
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
    home = escape(names.get(match.home, t.locale), quote=False)
    away = escape(names.get(match.away, t.locale), quote=False)
    kickoff = match.kickoff_at.astimezone(tz).strftime("%H:%M")
    return "\n".join(
        [
            title,
            "",
            f"<b>{home} — {away}</b>",
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
    day: date,
    matches: list[DayMatch],
    now: datetime,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
) -> str:
    """Foydalanuvchining sevimli klublari ishtirokidagi bugungi o'yinlar."""
    return "\n".join(
        [
            t("notify-morning-title"),
            *match_groups(day, matches, now, t, names, tz),
            "",
            t("matches-footer"),
        ]
    )
