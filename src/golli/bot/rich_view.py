"""O'yinlar ro'yxati va turnir jadvali — Telegram'ning "Rich Message" (jadvalli xabar) turida.

Bu turda haqiqiy jadval bor: ustunlarni Telegram ilovasining o'zi tekislaydi, shuning uchun
nomlarni bo'shliq bilan to'ldirish yoki qator enini harflab sanash kerak emas. Oddiy matnli
ko'rinish (views.py, standings_view.py) zaxira sifatida qoladi: Telegram jadvalli xabarni
qabul qilmasa, o'sha yuboriladi.
"""

import re
from datetime import date, datetime, tzinfo
from html import unescape

from aiogram.types import (
    InputRichBlockFooter,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichTextBold,
    RichTextCustomEmoji,
)
from babel.dates import format_datetime

from golli.bot import views
from golli.bot.standings_view import DIFFERENCE_LABEL
from golli.competitions import COMPETITIONS
from golli.db.standings import StandingRow
from golli.i18n import Translator
from golli.providers.base import MatchStatus
from golli.services.club_emoji import FALLBACK_EMOJI
from golli.services.schedule import DayMatch
from golli.services.team_names import TeamNames

# Sarlavha o'lchamlari (1 — eng katta, 6 — eng kichik).
TITLE_SIZE = 3
DAY_SIZE = 4
LEAGUE_SIZE = 5
# Boshlanmagan o'yinda klublar orasida turadigan belgi.
VERSUS = "–"

RichText = str | list | RichTextBold | RichTextCustomEmoji


def _plain(text: str) -> str:
    """Matn fayllaridagi HTML belgilaridan tozalangan matn (sarlavhalar o'zi qalin chiqadi)."""
    return unescape(re.sub(r"</?[bi]>", "", text))


def _heading(text: str, size: int) -> InputRichBlockSectionHeading:
    return InputRichBlockSectionHeading(text=_plain(text), size=size)


def _cell(
    text: RichText | None, align: str = "left", *, header: bool = False
) -> RichBlockTableCell:
    return RichBlockTableCell(
        text=text, align=align, valign="middle", is_header=True if header else None
    )


def _club(name: str, emoji_id: str | None) -> RichText:
    """Klub logotipi va nomi. Logotipi yo'q klubda ham o'rni band: ustun tekis tursin."""
    if emoji_id is None:
        return f"{FALLBACK_EMOJI} {name}"
    logo = RichTextCustomEmoji(custom_emoji_id=emoji_id, alternative_text=FALLBACK_EMOJI)
    return [logo, f" {name}"]


def _score(match: DayMatch, t: Translator) -> str:
    if match.home_score is None or match.away_score is None:
        return views.NO_SCORE
    score = f"{match.home_score}:{match.away_score}"
    if match.home_penalties is not None and match.away_penalties is not None:
        penalties = t("penalties", home=match.home_penalties, away=match.away_penalties)
        score += f" ({penalties})"
    return score


def _match_table(
    matches: list[DayMatch], now: datetime, t: Translator, names: TeamNames, tz: tzinfo
) -> tuple[InputRichBlockTable, list[str]]:
    """Bitta liganing o'yinlari jadvali va unga tegishli izohlar.

    Ustunlar: [soat yoki holat belgisi] | uy egasi | hisob yoki "–" | mehmon.
    Birinchi ustun faqat kerak bo'lganda chiqadi (hammasi tugagan o'yinlarda u bo'sh bo'lardi).
    """
    rows: list[tuple[str | None, RichText, DayMatch]] = []
    notes: list[str] = []
    for match in matches:
        if match.status is MatchStatus.FINISHED:
            lead, middle = None, RichTextBold(text=_score(match, t))
        elif match.status in views._STATUS_NOTES:
            icon, note = views._STATUS_NOTES[match.status]
            lead, middle = icon, VERSUS
            legend = f"{icon} — {t(note)}"
            if legend not in notes:
                notes.append(legend)
        elif views.is_live(match, now):
            lead, middle = views.LIVE_MARK, RichTextBold(text=_score(match, t))
        else:
            lead, middle = match.kickoff_at.astimezone(tz).strftime("%H:%M"), VERSUS
        rows.append((lead, middle, match))

    with_lead = any(lead is not None for lead, _, _ in rows)
    cells = []
    for lead, middle, match in rows:
        row = [
            _cell(_club(names.short(match.home, t.locale), match.home_emoji)),
            _cell(middle, "center"),
            _cell(_club(names.short(match.away, t.locale), match.away_emoji)),
        ]
        cells.append([_cell(lead), *row] if with_lead else row)
    return InputRichBlockTable(cells=cells, is_compact=True), notes


def _days_blocks(
    days: list[tuple[date, list[DayMatch]]],
    *,
    today: date,
    now: datetime,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
    day_size: int,
) -> list:
    blocks: list = []
    notes: list[str] = []
    for day, matches in days:
        blocks.append(_heading(views._title(day, today, t), day_size))
        if not matches:
            blocks.append(InputRichBlockParagraph(text=t("matches-none")))
            continue
        for competition in COMPETITIONS:
            group = [match for match in matches if match.competition == competition]
            if not group:
                continue
            table, table_notes = _match_table(group, now, t, names, tz)
            blocks += [_heading(t(f"competition-{competition}"), LEAGUE_SIZE), table]
            notes += [note for note in table_notes if note not in notes]

    all_matches = [match for _, matches in days for match in matches]
    # Vaqt mintaqasi haqidagi izoh faqat ro'yxatda boshlanish vaqti ko'rsatilganda kerak.
    if any(m.status is MatchStatus.SCHEDULED and not views.is_live(m, now) for m in all_matches):
        notes.append(t("matches-footer"))
    if any(views.is_live(match, now) for match in all_matches):
        notes.append(t("matches-live-note"))
    return [*blocks, *(InputRichBlockFooter(text=note) for note in notes)]


def days_message(
    days: list[tuple[date, list[DayMatch]]],
    *,
    today: date,
    now: datetime,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
) -> InputRichMessage:
    """Bir yoki bir nechta kunning o'yinlari: har kun sarlavha, har liga alohida jadval."""
    blocks = _days_blocks(days, today=today, now=now, t=t, names=names, tz=tz, day_size=TITLE_SIZE)
    return InputRichMessage(blocks=blocks)


def morning_message(
    days: list[tuple[date, list[DayMatch]]],
    *,
    today: date,
    now: datetime,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
) -> InputRichMessage:
    """Ertalabki eslatma: sevimli klublarning yaqin o'yinlari."""
    blocks = _days_blocks(days, today=today, now=now, t=t, names=names, tz=tz, day_size=DAY_SIZE)
    return InputRichMessage(blocks=[_heading(t("notify-morning-title"), TITLE_SIZE), *blocks])


def standings_message(
    competition: str,
    rows: list[StandingRow],
    updated_at: datetime,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
) -> InputRichMessage:
    """Turnir jadvali: o'rin, klub, o'yinlar, to'plar farqi, ochko."""
    header = [
        _cell("#", "right", header=True),
        _cell(t("standings-col-club"), header=True),
        _cell(t("standings-col-played"), "right", header=True),
        _cell(DIFFERENCE_LABEL, "right", header=True),
        _cell(t("standings-col-points"), "right", header=True),
    ]
    blocks: list = [_heading(t(f"competition-{competition}"), TITLE_SIZE)]
    group: str | None = None
    cells: list[list[RichBlockTableCell]] = []

    def flush() -> None:
        if cells:
            table = InputRichBlockTable(cells=[header, *cells], is_compact=True, is_striped=True)
            blocks.append(table)
            cells.clear()

    for row in rows:
        if row.group != group:
            # Guruhlarga bo'lingan turnirda har guruh o'z nomi va o'z jadvali bilan chiqadi.
            flush()
            group = row.group
            if group:
                blocks.append(_heading(group, LEAGUE_SIZE))
        # Farq ishorasi bilan (+14, -7); nol bo'lsa ishorasiz.
        difference = f"{row.goal_difference:+d}" if row.goal_difference else "0"
        cells.append(
            [
                _cell(str(row.position), "right"),
                _cell(_club(names.short(row.team, t.locale), row.team_emoji)),
                _cell(str(row.played), "right"),
                _cell(difference, "right"),
                _cell(RichTextBold(text=str(row.points)), "right"),
            ]
        )
    flush()

    updated = format_datetime(updated_at.astimezone(tz), t("datetime-format"), locale=t.locale)
    blocks += [
        InputRichBlockFooter(text=t("standings-updated", time=updated)),
    ]
    return InputRichMessage(blocks=blocks)
