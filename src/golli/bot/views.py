"""O'yinlar ro'yxatini foydalanuvchi tilida matnga aylantirish."""

from datetime import date, datetime, timedelta, tzinfo
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from babel.dates import format_date

from golli.bot.callbacks import DayCallback, UpcomingCallback
from golli.competitions import COMPETITIONS
from golli.i18n import Translator
from golli.providers.base import MatchStatus
from golli.services.schedule import DayMatch
from golli.services.team_names import TeamNames

_STATUS_NOTES = {
    MatchStatus.POSTPONED: ("⏸", "status-postponed"),
    MatchStatus.SUSPENDED: ("⏸", "status-suspended"),
    MatchStatus.CANCELLED: ("❌", "status-cancelled"),
}


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


def _after_midnight(match: DayMatch, day: date, tz: tzinfo) -> bool:
    """Futbol kuniga kiradi, lekin taqvim bo'yicha ertasi kuni boshlanadi (00:00–06:00)."""
    return match.kickoff_at.astimezone(tz).date() != day


def _upcoming(match: DayMatch, now: datetime) -> bool:
    return match.status is MatchStatus.SCHEDULED and match.kickoff_at > now


def _match_line(
    match: DayMatch, day: date, now: datetime, t: Translator, names: TeamNames, tz: tzinfo
) -> str:
    home = escape(names.get(match.home, t.locale), quote=False)
    away = escape(names.get(match.away, t.locale), quote=False)
    has_score = match.home_score is not None and match.away_score is not None
    score = f"<b>{match.home_score}:{match.away_score}</b>" if has_score else "—"

    if match.status is MatchStatus.FINISHED:
        return f"✅ {score_line(match, t, names)}"
    if match.status in _STATUS_NOTES:
        icon, note = _STATUS_NOTES[match.status]
        return f"{icon} {home} — {away} · {t(note)}"
    if is_live(match, now):
        return f"🔴 {home} {score} {away}"
    kickoff = match.kickoff_at.astimezone(tz).strftime("%H:%M")
    # 🌙: vaqt ro'yxat sarlavhasidagi sanaga emas, undan keyingi kechaga tegishli.
    night = "🌙 " if _after_midnight(match, day, tz) else ""
    return f"{night}{kickoff}  {home} — {away}"


def match_groups(
    day: date, matches: list[DayMatch], now: datetime, t: Translator, names: TeamNames, tz: tzinfo
) -> list[str]:
    """Bir kunning o'yinlari ligalar bo'yicha; har bir guruh oldida bo'sh qator."""
    lines: list[str] = []
    for competition in COMPETITIONS:
        group = [match for match in matches if match.competition == competition]
        if not group:
            continue
        lines += ["", f"<b>{t('competition-' + competition)}</b>"]
        lines += [_match_line(match, day, now, t, names, tz) for match in group]

    if any(_upcoming(match, now) and _after_midnight(match, day, tz) for match in matches):
        next_date = format_date(day + timedelta(days=1), t("date-short-format"), locale=t.locale)
        lines += ["", t("matches-night-note", date=next_date)]
    return lines


def score_line(match: DayMatch, t: Translator, names: TeamNames) -> str:
    """ "Arsenal <b>2:1</b> Chelsi (pen. 4:3)" — tugagan o'yin uchun."""
    home = escape(names.get(match.home, t.locale), quote=False)
    away = escape(names.get(match.away, t.locale), quote=False)
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
    return [title, *match_groups(day, matches, now, t, names, tz)]


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
    if all_matches:
        lines += ["", t("matches-footer")]
    if any(is_live(match, now) for match in all_matches):
        lines.append(t("matches-live-note"))
    return "\n".join(lines)


def render_no_upcoming(t: Translator) -> str:
    return f"<b>{t('menu-matches')}</b>\n\n{t('matches-none-upcoming')}"


def _short(day: date, t: Translator) -> str:
    return f"{format_date(day, 'EEE', locale=t.locale)} {day:%d.%m}"


def day_navigation(
    first: date,
    last: date,
    match_days: list[date],
    t: Translator,
    *,
    back_to_upcoming: bool,
) -> InlineKeyboardMarkup | None:
    """Ko'rsatilgan kunlardan (first..last) oldingi va keyingi o'yin kuniga o'tish tugmalari.

    O'yinsiz kunlar tashlab ketiladi. Bitta kun ko'rilayotganda o'rtada asosiy
    ro'yxatga ("Yaqin o'yinlar") qaytish tugmasi turadi.
    """

    def day_button(text: str, target: date) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text, callback_data=DayCallback(day=target.isoformat()).pack()
        )

    previous = max((d for d in match_days if d < first), default=None)
    following = min((d for d in match_days if d > last), default=None)
    row = []
    if previous is not None:
        row.append(day_button(f"◀️ {_short(previous, t)}", previous))
    if back_to_upcoming:
        row.append(
            InlineKeyboardButton(text=t("menu-matches"), callback_data=UpcomingCallback().pack())
        )
    if following is not None:
        row.append(day_button(f"{_short(following, t)} ▶️", following))
    return InlineKeyboardMarkup(inline_keyboard=[row]) if row else None
