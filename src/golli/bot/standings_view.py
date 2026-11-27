"""Turnir jadvalining matni.

Telegram'da haqiqiy jadval yo'q, shuning uchun ustunlar teng enli (monospace) shrift bilan
tekislanadi. Har qator uch qismdan iborat: o'rin, klub logotipi va qolgan ustunlar. Logotip
<code> ichida tura olmaydi (Telegram unga boshqa formatlashni joylashtirmaydi), shu sababli
u ikki <code> bo'lagi orasida, hamma qatorda bir xil joyda turadi.
"""

from datetime import datetime, tzinfo
from html import escape

from babel.dates import format_datetime

from golli.bot.views import VERSUS, fit_entities
from golli.competitions import STAGE_ORDER
from golli.db.standings import StandingRow
from golli.i18n import Translator
from golli.services.club_emoji import FALLBACK_EMOJI
from golli.services.knockout import Tie
from golli.services.schedule import DayMatch
from golli.services.team_names import TeamNames

# Sarlavha qatorida logotip o'rnini egallaydi: ustunlar klub qatorlari bilan bir chiziqda tursin.
HEADER_ICON = "📊"
DIFFERENCE_LABEL = "+/-"


def _code(text: str) -> str:
    return f"<code>{escape(text, quote=False)}</code>"


def _line(
    position: str, logo: str, club: str, played: str, difference: str, points: str, width: int
) -> str:
    """Bitta qator: o'rin, logotip, keyin klub, o'yinlar, to'plar farqi va ochko."""
    cells = f"{club:<{width}} {played:>2} {difference:>3} {points:>2}"
    return f"{_code(f'{position:>2}')} {logo} {_code(cells)}"


def _logo(emoji_id: str | None) -> str:
    if emoji_id is None:
        return FALLBACK_EMOJI
    return f'<tg-emoji emoji-id="{emoji_id}">{FALLBACK_EMOJI}</tg-emoji>'


def render_standings(
    competition: str,
    rows: list[StandingRow],
    updated_at: datetime | None,
    t: Translator,
    names: TeamNames,
    tz: tzinfo,
) -> str:
    title = f"<b>{t(f'competition-{competition}')}</b>"
    if not rows or updated_at is None:
        return f"{title}\n\n{t('standings-empty')}"

    # Klub nomlari qisqa shaklda: qator telefonda bitta satrga sig'ishi kerak.
    clubs = [names.short(row.team, t.locale) for row in rows]
    club_label = t("standings-col-club")
    width = max(len(name) for name in [*clubs, club_label])
    header = _line(
        "#",
        HEADER_ICON,
        club_label,
        t("standings-col-played"),
        DIFFERENCE_LABEL,
        t("standings-col-points"),
        width,
    )

    lines = [title, "", header]
    group = rows[0].group
    for row, club in zip(rows, clubs, strict=True):
        if row.group != group:
            lines.append("")
        if row.group and (row.group != group or row is rows[0]):
            # Guruhlarga bo'lingan turnirda har guruh o'z nomi bilan boshlanadi.
            lines.append(f"<b>{escape(row.group, quote=False)}</b>")
        group = row.group
        # Farq ishorasi bilan (+14, -7); nol bo'lsa ishorasiz.
        difference = f"{row.goal_difference:+d}" if row.goal_difference else "0"
        lines.append(
            _line(
                str(row.position),
                _logo(row.team_emoji),
                club,
                str(row.played),
                difference,
                str(row.points),
                width,
            )
        )

    updated = format_datetime(updated_at.astimezone(tz), t("datetime-format"), locale=t.locale)
    lines += ["", t("standings-updated", time=updated)]
    # Katta jadval (Chempionlar ligasi, 36 qator) limitga sig'maydi: unda qator oxiridagi bo'lak
    # keyingi qator boshidagi bilan ulanadi va qatoriga uchta emas, ikkita element sarflanadi.
    return fit_entities("\n".join(lines))


def render_knockout(
    competition: str, ties: list[Tie], t: Translator, names: TeamNames, tz: tzinfo
) -> str:
    """Pley-off juftliklari oddiy matnda (jadvalli xabar o'tmagan holat uchun)."""
    lines = [f"<b>{t(f'competition-{competition}')}</b>"]
    for stage in STAGE_ORDER:
        stage_ties = [tie for tie in ties if tie.stage == stage]
        if not stage_ties:
            continue
        lines += ["", f"<b>{t(f'stage-{stage}')}</b>"]
        for tie in stage_ties:
            home = escape(names.short(tie.first.home, t.locale), quote=False)
            away = escape(names.short(tie.first.away, t.locale), quote=False)
            scores = [_leg_text(tie.first, tz)]
            if tie.second is not None:
                scores.append(_leg_text(tie.second, tz, flipped=True))
            lines.append(f"{home}{VERSUS}{away}: {', '.join(scores)}")
    return "\n".join(lines)


def _leg_text(match: DayMatch, tz: tzinfo, *, flipped: bool = False) -> str:
    """O'ynalgan o'yin hisobi (juftlik tartibida) yoki o'ynalmagan o'yin sanasi."""
    if match.home_score is None or match.away_score is None:
        return match.kickoff_at.astimezone(tz).strftime("%d.%m")
    home, away = match.home_score, match.away_score
    return f"{away}:{home}" if flipped else f"{home}:{away}"
