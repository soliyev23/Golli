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
from golli.competitions import STAGE_ORDER
from golli.db.standings import StandingRow
from golli.i18n import Translator
from golli.providers.base import MatchStatus
from golli.services.club_emoji import FALLBACK_EMOJI
from golli.services.knockout import Tie, advancing_side, aggregate_of
from golli.services.schedule import DayMatch
from golli.services.team_names import TeamNames

# Sarlavha o'lchamlari (1 — eng katta, 6 — eng kichik).
TITLE_SIZE = 3
DAY_SIZE = 4
LEAGUE_SIZE = 5
# Boshlanmagan o'yinda klublar orasida turadigan belgi.
VERSUS = "–"
NBSP = "\u00a0"

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


def _club(name: str, emoji_id: str | None, *, nowrap: bool = False, bold: bool = False) -> RichText:
    """Klub logotipi va nomi. Logotipi yo'q klubda ham o'rni band: ustun tekis tursin.

    `nowrap` — bo'shliqlar bo'linmaydigan bo'shliqqa almashtiriladi: tor ustunda ham
    "Real Madrid" ikki qatorga bo'linib ketmaydi. `bold` — nom qalin yoziladi (pley-offda
    keyingi bosqichga chiqqan klub).
    """
    space = NBSP if nowrap else " "
    name = name.replace(" ", space)
    shown: RichText = RichTextBold(text=name) if bold else name
    if emoji_id is None:
        return [f"{FALLBACK_EMOJI}{space}", shown] if bold else f"{FALLBACK_EMOJI}{space}{name}"
    logo = RichTextCustomEmoji(custom_emoji_id=emoji_id, alternative_text=FALLBACK_EMOJI)
    return [logo, space, shown] if bold else [logo, f"{space}{name}"]


def _score(match: DayMatch, t: Translator) -> RichText:
    """Hisob qalin yozuvda; javob o'yinida yonida ikki o'yin yig'indisi, kerak bo'lsa penaltilar."""
    has_score = match.home_score is not None and match.away_score is not None
    score = f"{match.home_score}:{match.away_score}" if has_score else views.NO_SCORE
    extra = ""
    if total := views.aggregate_text(match):
        extra += f" {total}"
    if match.home_penalties is not None and match.away_penalties is not None:
        penalties = t("penalties", home=match.home_penalties, away=match.away_penalties)
        extra += f" ({penalties})"
    return [RichTextBold(text=score), extra] if extra else RichTextBold(text=score)


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
            lead, middle = None, _score(match, t)
        elif match.status in views._STATUS_NOTES:
            icon, note = views._STATUS_NOTES[match.status]
            lead, middle = icon, VERSUS
            legend = f"{icon} — {t(note)}"
            if legend not in notes:
                notes.append(legend)
        elif views.is_live(match, now):
            lead, middle = views.LIVE_MARK, _score(match, t)
        else:
            # Javob o'yini hali boshlanmagan: chiziqcha yonida birinchi o'yindan keyingi yig'indi.
            total = views.aggregate_text(match)
            lead = match.kickoff_at.astimezone(tz).strftime("%H:%M")
            middle = f"{VERSUS} {total}" if total else VERSUS
        rows.append((lead, middle, match))

    with_lead = any(lead is not None for lead, _, _ in rows)
    cells = []
    for lead, middle, match in rows:
        # Pley-offda keyingi bosqichga chiqqan klub nomi qalin yoziladi.
        winner = advancing_side(match)
        home = _club(names.short(match.home, t.locale), match.home_emoji, bold=winner == "home")
        away = _club(names.short(match.away, t.locale), match.away_emoji, bold=winner == "away")
        row = [_cell(home), _cell(middle, "center"), _cell(away)]
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
        for competition, stage, group in views.league_groups(matches):
            table, table_notes = _match_table(group, now, t, names, tz)
            blocks += [_heading(views.league_title(competition, stage, t), LEAGUE_SIZE), table]
            notes += [note for note in table_notes if note not in notes]

    all_matches = [match for _, matches in days for match in matches]
    # Vaqt mintaqasi haqidagi izoh faqat ro'yxatda boshlanish vaqti ko'rsatilganda kerak.
    if any(m.status is MatchStatus.SCHEDULED and not views.is_live(m, now) for m in all_matches):
        notes.append(t("matches-footer"))
    if any(views.is_live(match, now) for match in all_matches):
        notes.append(t("matches-live-note"))
    if any(aggregate_of(m) for m in all_matches if m.status not in views._STATUS_NOTES):
        notes.append(t("matches-aggregate-note"))
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
    """Turnir jadvali: o'rin, klub, o'yinlar, g'alaba, durang, mag'lubiyat, to'plar, ochko.

    Ustunlar soni ikki telefonda sinab tanlangan. Kam bo'lsa, jadval Android'da ekranning bir
    qisminigina egallaydi (Telegram xabar enini ichidagi eng keng narsaga qarab belgilaydi).
    Ko'p bo'lsa (to'plar farqi ham qo'shilsa), iPhone'da klub ustuni torayib, ikki so'zli nom
    ikki qatorga bo'linadi. Shuning uchun farq ustuni yo'q, klub nomi esa bo'linmaydi.
    """
    header = [
        _cell("#", "right", header=True),
        _cell(t("standings-col-club"), header=True),
        _cell(t("standings-col-played"), "right", header=True),
        _cell(t("standings-col-wins"), "right", header=True),
        _cell(t("standings-col-draws"), "right", header=True),
        _cell(t("standings-col-losses"), "right", header=True),
        _cell(t("standings-col-goals"), "center", header=True),
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
        cells.append(
            [
                _cell(str(row.position), "right"),
                _cell(_club(names.short(row.team, t.locale), row.team_emoji, nowrap=True)),
                _cell(str(row.played), "right"),
                _cell(str(row.wins), "right"),
                _cell(str(row.draws), "right"),
                _cell(str(row.losses), "right"),
                _cell(f"{row.goals_for}:{row.goals_against}", "center"),
                _cell(RichTextBold(text=str(row.points)), "right"),
            ]
        )
    flush()

    updated = format_datetime(updated_at.astimezone(tz), t("datetime-format"), locale=t.locale)
    blocks += [
        InputRichBlockFooter(text=t("standings-updated", time=updated)),
    ]
    return InputRichMessage(blocks=blocks)


# --- Pley-off juftliklari


def _leg(match: DayMatch | None, tz: tzinfo, *, flipped: bool = False) -> str:
    """Bitta o'yin katagi: o'ynalgan bo'lsa hisob, bo'lmasa sanasi.

    `flipped` — javob o'yini: unda klublar joy almashgan, hisob esa juftlik tartibida yoziladi.
    """
    if match is None:
        return VERSUS
    if match.home_score is None or match.away_score is None:
        return match.kickoff_at.astimezone(tz).strftime("%d.%m")
    home, away = match.home_score, match.away_score
    return f"{away}:{home}" if flipped else f"{home}:{away}"


def _tie_total(tie: Tie, t: Translator) -> RichText | None:
    """Ikki o'yin yig'indisi (juftlik tartibida), kerak bo'lsa penaltilar bilan."""
    legs = [
        leg for leg in (tie.first, tie.second) if leg is not None and leg.home_score is not None
    ]
    if not legs:
        return None
    left = sum(m.home_score if m is tie.first else m.away_score for m in legs)
    right = sum(m.away_score if m is tie.first else m.home_score for m in legs)
    total: list = [RichTextBold(text=f"{left}:{right}")]
    decider = tie.second or tie.first
    if decider.home_penalties is not None and decider.away_penalties is not None:
        flipped = decider is tie.second
        home = decider.away_penalties if flipped else decider.home_penalties
        away = decider.home_penalties if flipped else decider.away_penalties
        total.append(f" ({t('penalties', home=home, away=away)})")
    return total


def _tie_winner(tie: Tie) -> str | None:
    """Keyingi bosqichga chiqqan klub juftlikning qaysi tomonida: "left", "right" yoki None."""
    decider = tie.second or tie.first
    side = advancing_side(decider)
    if side is None:
        return None
    if decider is tie.second:
        # Javob o'yinida mezbon — juftlikning o'ng tomonidagi klub.
        return "right" if side == "home" else "left"
    return "left" if side == "home" else "right"


def knockout_message(
    competition: str, ties: list[Tie], t: Translator, names: TeamNames, tz: tzinfo
) -> InputRichMessage:
    """Pley-off juftliklari, eng so'nggi bosqich tepada.

    Ikki o'yinli bosqich ustunlari: klub | 1-o'yin | 2-o'yin | jami | klub. Hisoblar juftlik
    tartibida (chapdagi klub gollari oldin). Keyingi bosqichga chiqqan klub nomi qalin.
    """
    blocks: list = [_heading(t(f"competition-{competition}"), TITLE_SIZE)]
    for stage in STAGE_ORDER:
        stage_ties = [tie for tie in ties if tie.stage == stage]
        if not stage_ties:
            continue
        two_legged = any(tie.second is not None for tie in stage_ties)
        cells: list[list[RichBlockTableCell]] = []
        if two_legged:
            cells.append(
                [
                    _cell(None, header=True),
                    _cell("1", "center", header=True),
                    _cell("2", "center", header=True),
                    _cell(t("knockout-col-total"), "center", header=True),
                    _cell(None, header=True),
                ]
            )
        for tie in stage_ties:
            winner = _tie_winner(tie)
            first = tie.first
            left = _club(names.short(first.home, t.locale), first.home_emoji, bold=winner == "left")
            right = _club(
                names.short(first.away, t.locale), first.away_emoji, bold=winner == "right"
            )
            if two_legged:
                middle = [
                    _cell(_leg(first, tz), "center"),
                    _cell(_leg(tie.second, tz, flipped=True), "center"),
                    _cell(_tie_total(tie, t) or VERSUS, "center"),
                ]
            else:
                middle = [_cell(_tie_total(tie, t) or _leg(first, tz), "center")]
            cells.append([_cell(left), *middle, _cell(right)])
        blocks += [
            _heading(t(f"stage-{stage}"), LEAGUE_SIZE),
            InputRichBlockTable(cells=cells, is_compact=True),
        ]
    return InputRichMessage(blocks=blocks)
