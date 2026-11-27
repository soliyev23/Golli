"""O'yinlar ro'yxatini foydalanuvchi tilida matnga aylantirish."""

from datetime import date, datetime, timedelta, tzinfo
from html import escape

from babel.dates import format_date

from golli.competitions import COMPETITIONS
from golli.i18n import Translator
from golli.providers.base import MatchStatus
from golli.services.club_emoji import FALLBACK_EMOJI
from golli.services.schedule import DayMatch
from golli.services.team_names import TeamNames

_STATUS_NOTES = {
    MatchStatus.POSTPONED: ("⏸", "status-postponed"),
    MatchStatus.SUSPENDED: ("⏸", "status-suspended"),
    MatchStatus.CANCELLED: ("❌", "status-cancelled"),
}


# O'yin qatorida ikki klub orasidagi ajratgich. Qator telefonda bitta satrga sig'ishi uchun
# qisqa chiziqcha (–) va klublarning qisqa nomlari ishlatiladi.
VERSUS = " – "


def club_label(
    name: str, emoji_id: str | None, t: Translator, names: TeamNames, *, short: bool = False
) -> str:
    """Klub nomi foydalanuvchi tilida; logotipi bo'lsa, nom oldida maxsus emoji turadi.

    `short` — o'yin qatorlari uchun qisqa nom ("Manchester Yunayted" o'rniga "MYU").
    """
    shown = names.short(name, t.locale) if short else names.get(name, t.locale)
    label = escape(shown, quote=False)
    if emoji_id is None:
        return label
    return f'<tg-emoji emoji-id="{emoji_id}">{FALLBACK_EMOJI}</tg-emoji> {label}'


def is_live(match: DayMatch, now: datetime) -> bool:
    # Boshlanish vaqti o'tgan, lekin holati hali olinmagan o'yin ham jonli deb ko'rsatiladi.
    return match.status is MatchStatus.LIVE or (
        match.status is MatchStatus.SCHEDULED and match.kickoff_at <= now
    )


def _title(day: date, today: date, t: Translator) -> str:
    key = {
        today: "matches-title-today",
        today + timedelta(days=1): "matches-title-tomorrow",
        today - timedelta(days=1): "matches-title-yesterday",
    }.get(day, "matches-title-day")
    return t(key, date=format_date(day, t("date-format"), locale=t.locale))


def _match_line(match: DayMatch, now: datetime, t: Translator, names: TeamNames, tz: tzinfo) -> str:
    home = club_label(match.home, match.home_emoji, t, names, short=True)
    away = club_label(match.away, match.away_emoji, t, names, short=True)
    has_score = match.home_score is not None and match.away_score is not None
    score = f"<b>{match.home_score}:{match.away_score}</b>" if has_score else VERSUS.strip()

    if match.status is MatchStatus.FINISHED:
        return score_line(match, t, names)
    if match.status in _STATUS_NOTES:
        icon, note = _STATUS_NOTES[match.status]
        return f"{icon} {home}{VERSUS}{away} · {t(note)}"
    if is_live(match, now):
        return f"🔴 {home} {score} {away}"
    kickoff = match.kickoff_at.astimezone(tz).strftime("%H:%M")
    return f"{kickoff} {home}{VERSUS}{away}"


def match_groups(
    matches: list[DayMatch], now: datetime, t: Translator, names: TeamNames, tz: tzinfo
) -> list[str]:
    """Bir kunning o'yinlari ligalar bo'yicha; har bir guruh oldida bo'sh qator."""
    lines: list[str] = []
    for competition in COMPETITIONS:
        group = [match for match in matches if match.competition == competition]
        if not group:
            continue
        lines += ["", f"<b>{t('competition-' + competition)}</b>"]
        lines += [_match_line(match, now, t, names, tz) for match in group]
    return lines


def score_line(match: DayMatch, t: Translator, names: TeamNames) -> str:
    """ "Arsenal <b>2:1</b> Chelsi (pen. 4:3)" — tugagan o'yin uchun."""
    home = club_label(match.home, match.home_emoji, t, names, short=True)
    away = club_label(match.away, match.away_emoji, t, names, short=True)
    line = f"{home} <b>{match.home_score}:{match.away_score}</b> {away}"
    if match.home_penalties is not None and match.away_penalties is not None:
        penalties = t("penalties", home=match.home_penalties, away=match.away_penalties)
        line += f" ({penalties})"
    return line


def _day_block(
    day: date,
    matches: list[DayMatch],
    today: date,
    now: datetime,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
) -> list[str]:
    title = _title(day, today, t)
    if not matches:
        return [title, "", t("matches-none")]
    return [title, *match_groups(matches, now, t, names, tz)]


def render_days(
    days: list[tuple[date, list[DayMatch]]],
    *,
    today: date,
    now: datetime,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
) -> str:
    """Bir yoki bir nechta kunning o'yinlari bitta xabarda; izohlar oxirida bir marta."""
    lines: list[str] = []
    for day, matches in days:
        if lines:
            lines.append("")
        lines += _day_block(day, matches, today, now, t, names, tz)

    all_matches = [match for _, matches in days for match in matches]
    notes = []
    # Vaqt mintaqasi haqidagi izoh faqat ro'yxatda boshlanish vaqti ko'rsatilganda kerak.
    if any(
        match.status is MatchStatus.SCHEDULED and not is_live(match, now) for match in all_matches
    ):
        notes.append(t("matches-footer"))
    if any(is_live(match, now) for match in all_matches):
        notes.append(t("matches-live-note"))
    if notes:
        lines += ["", *notes]
    return "\n".join(lines)


def render_no_upcoming(t: Translator) -> str:
    return f"<b>{t('menu-matches')}</b>\n\n{t('matches-none-upcoming')}"


def render_no_recent(t: Translator) -> str:
    return f"<b>{t('menu-recent')}</b>\n\n{t('matches-none-recent')}"
