"""O'yinlar ro'yxatini foydalanuvchi tilida matnga aylantirish.

Telegram'da jadval yo'q, shuning uchun ustunlar teng enli (<code>) shrift bilan tekislanadi:
uy egasi nomi bo'shliqlar bilan to'ldiriladi va barcha qatorlarda mehmon klub (logotipi bilan)
bir joydan boshlanadi. Logotip <code> ichida tura olmaydi, shu sababli u bo'laklar orasida.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from html import escape

from babel.dates import format_date

from golli.competitions import COMPETITIONS
from golli.i18n import Translator
from golli.providers.base import MatchStatus
from golli.services.club_emoji import FALLBACK_EMOJI
from golli.services.knockout import aggregate_of, stage_of
from golli.services.schedule import DayMatch
from golli.services.team_names import TeamNames

_STATUS_NOTES = {
    MatchStatus.POSTPONED: ("⏸", "status-postponed"),
    MatchStatus.SUSPENDED: ("⏸", "status-suspended"),
    MatchStatus.CANCELLED: ("❌", "status-cancelled"),
}


# Hisobi hali yo'q (yoki bo'lmaydigan) o'yin uchun hisob o'rnidagi yozuv.
NO_SCORE = "–:–"
LIVE_MARK = "🔴"
# Bitta qatordagi teng enli belgilar soni chegarasi (soat yoki hisob, ikkala klub nomi).
# Shundan uzun qator telefonda ikkiga bo'linadi: foydalanuvchi skrinshotidan o'lchangan —
# teng enli harf 0,53 em, logotip bo'shliqlari bilan 2,07 em, sig'adigan qator ~17 em.
ROW_CHARS = 25
# Boshlanmagan o'yin qatorida uy egasi nomidan keyin (mehmon klub logotipi oldidan) turadigan
# belgi, masalan " -". Bo'sh: klublarni logotipning o'zi ajratadi. Belgi qator enidan joy oladi,
# shuning uchun u bilan uzun nomli juftliklarda tekislash ko'proq qisqaradi.
UPCOMING_SEPARATOR = ""
# Jonli o'yin belgisi (🔴) qator oxirida shuncha harf enicha joy oladi.
LIVE_MARK_CHARS = 3
# Telegram bitta xabarda shuncha formatlash elementini saqlaydi, ortig'ini tashlab yuboradi
# (2026-11-27 da sinab ko'rilgan: 130 tadan 100 tasi qaytdi).
MAX_ENTITIES = 100

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


def league_groups(matches: list[DayMatch]) -> list[tuple[str, str | None, list[DayMatch]]]:
    """Bir kunning o'yinlari ligalar bo'yicha: (liga, pley-off bosqichi yoki None, o'yinlar).

    Bitta ligada har xil bosqich o'yinlari bo'lsa (kam uchraydi), har bosqich alohida guruh.
    """
    groups: list[tuple[str, str | None, list[DayMatch]]] = []
    for competition in COMPETITIONS:
        stages: dict[str | None, list[DayMatch]] = {}
        for match in matches:
            if match.competition == competition:
                stages.setdefault(stage_of(match), []).append(match)
        groups += [(competition, stage, group) for stage, group in stages.items()]
    return groups


def league_title(competition: str, stage: str | None, t: Translator) -> str:
    """Liga nomi; pley-off o'yinlarida bosqich nomi bilan: "Chempionlar ligasi · 1/8 final"."""
    title = t(f"competition-{competition}")
    return f"{title} · {t(f'stage-{stage}')}" if stage else title


def aggregate_text(match: DayMatch) -> str | None:
    """Javob o'yinidagi ikki o'yin yig'indisi "(3:2)" ko'rinishida; yig'indi bo'lmasa None."""
    total = aggregate_of(match)
    return f"({total[0]}:{total[1]})" if total else None


def entity_count(text: str) -> int:
    """HTML matndagi formatlash elementlari soni (Telegram limiti bilan solishtirish uchun)."""
    return sum(text.count(tag) for tag in ("<code>", "<tg-emoji", "<b>", "<i>"))


def fit_entities(text: str) -> str:
    """Matnni Telegram'ning formatlash elementlari limitiga sig'diradi.

    Avval qo'shni qatorlarning teng enli bo'laklari ulanadi (ko'rinish o'zgarmaydi). Shunda ham
    sig'masa (juda gavjum kunlar), teng enli format olib tashlanadi: ustunlar tekisligi
    yo'qoladi, lekin matn va logotiplar saqlanadi.
    """
    if entity_count(text) > MAX_ENTITIES:
        text = text.replace("</code>\n<code>", "\n")
    if entity_count(text) > MAX_ENTITIES:
        text = re.sub(r" {2,}", " ", text.replace("<code>", "").replace("</code>", ""))
    return text


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


def _code(text: str) -> str:
    return f"<code>{escape(text, quote=False)}</code>"


def _logo(emoji_id: str | None) -> str:
    # Logotipi yo'q klubda ham shu o'rin band qilinadi: ustunlar siljimasin.
    if emoji_id is None:
        return FALLBACK_EMOJI
    return f'<tg-emoji emoji-id="{emoji_id}">{FALLBACK_EMOJI}</tg-emoji>'


@dataclass(slots=True)
class _Row:
    """Bitta o'yin qatori uchun tayyor bo'laklar."""

    home: str
    away: str
    home_logo: str
    away_logo: str
    # Boshlanmagan o'yinda — boshlanish soati; qolganlarida None (ular hisob bilan chiqadi).
    kickoff: str | None
    # Klublar orasidagi yozuv: hisob yoki NO_SCORE.
    middle: str
    # Qator oxiriga qo'shiladigan izoh: jonli belgi, penaltilar, "ko'chirilgan".
    suffix: str
    # Qator oxiridagi izoh uchun qoldiriladigan joy (teng enli harflarda).
    reserved: int


def _row(match: DayMatch, now: datetime, t: Translator, names: TeamNames, tz: tzinfo) -> _Row:
    has_score = match.home_score is not None and match.away_score is not None
    row = _Row(
        home=names.short(match.home, t.locale),
        away=names.short(match.away, t.locale),
        home_logo=_logo(match.home_emoji),
        away_logo=_logo(match.away_emoji),
        kickoff=None,
        middle=f"{match.home_score}:{match.away_score}" if has_score else NO_SCORE,
        suffix="",
        reserved=0,
    )
    # Javob o'yinida qator oxirida ikki o'yin yig'indisi turadi.
    total = aggregate_text(match)
    if total and match.status not in _STATUS_NOTES:
        row.suffix, row.reserved = f" {total}", len(total) + 1
    if match.status is MatchStatus.FINISHED:
        if match.home_penalties is not None and match.away_penalties is not None:
            penalties = t("penalties", home=match.home_penalties, away=match.away_penalties)
            row.suffix += f" ({penalties})"
    elif match.status in _STATUS_NOTES:
        icon, note = _STATUS_NOTES[match.status]
        row.middle, row.suffix = NO_SCORE, f" {icon} {t(note)}"
    elif is_live(match, now):
        row.suffix += f" {LIVE_MARK}"
        row.reserved += LIVE_MARK_CHARS
    else:
        row.kickoff = match.kickoff_at.astimezone(tz).strftime("%H:%M")
    return row


def _padding(row: _Row, widest: int, taken: int) -> int:
    """Uy egasi nomi necha belgiga to'ldirilishi: ustun eni, lekin qator chegaradan oshmasin.

    `taken` — qatordagi boshqa teng enli belgilar (soat yoki hisob). Juda uzun juftlikda
    to'ldirish qisqaradi: mehmon klub biroz chaproqdan boshlanadi, lekin qator bo'linmaydi.
    """
    room = ROW_CHARS - taken - row.reserved - len(row.away)
    return min(widest, max(len(row.home), room))


def _match_lines(
    matches: list[DayMatch], now: datetime, t: Translator, names: TeamNames, tz: tzinfo
) -> list[str]:
    """Bitta liganing o'yinlari. Ikki xil qator bor, har biri o'z ustunlari bilan:

    - boshlanmagan o'yin:  20:00 [logo] Uy egasi   [logo] Mehmon
    - hisobli o'yin:       [logo] Uy egasi   2:1 [logo] Mehmon
    """
    rows = [_row(match, now, t, names, tz) for match in matches]
    upcoming = [row for row in rows if row.kickoff is not None]
    scored = [row for row in rows if row.kickoff is None]
    upcoming_width = max((len(row.home) for row in upcoming), default=0)
    scored_width = max((len(row.home) for row in scored), default=0)
    middle_width = max((len(row.middle) for row in scored), default=0)

    lines = []
    for row in rows:
        away = f"{row.away_logo} {_code(row.away)}{row.suffix}"
        if row.kickoff is not None:
            taken = len(row.kickoff) + len(UPCOMING_SEPARATOR)
            home = row.home.ljust(_padding(row, upcoming_width, taken)) + UPCOMING_SEPARATOR
            lines.append(f"{_code(row.kickoff)} {row.home_logo} {_code(home)} {away}")
        else:
            home = row.home.ljust(_padding(row, scored_width, middle_width + 1))
            middle = row.middle.center(middle_width)
            lines.append(f"{row.home_logo} {_code(f'{home} {middle}')} {away}")
    return lines


def match_groups(
    matches: list[DayMatch], now: datetime, t: Translator, names: TeamNames, tz: tzinfo
) -> list[str]:
    """Bir kunning o'yinlari ligalar bo'yicha; har bir guruh oldida bo'sh qator."""
    lines: list[str] = []
    for competition, stage, group in league_groups(matches):
        lines += ["", f"<b>{league_title(competition, stage, t)}</b>"]
        lines += _match_lines(group, now, t, names, tz)
    return lines


def score_line(match: DayMatch, t: Translator, names: TeamNames) -> str:
    """ "Arsenal <b>2:1</b> Chelsi (pen. 4:3)" — natija eslatmasidagi bitta o'yin uchun."""
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
    if any(aggregate_of(match) for match in all_matches if match.status not in _STATUS_NOTES):
        notes.append(t("matches-aggregate-note"))
    if notes:
        lines += ["", *notes]
    return fit_entities("\n".join(lines))


def render_no_upcoming(t: Translator) -> str:
    return f"<b>{t('menu-matches')}</b>\n\n{t('matches-none-upcoming')}"


def render_no_recent(t: Translator) -> str:
    return f"<b>{t('menu-recent')}</b>\n\n{t('matches-none-recent')}"
