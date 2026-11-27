"""Sevimli klublar bo'limining matnlari va pastki (reply) klaviaturalari.

Bo'lim ikki bosqichli: avval liga tanlanadi, keyin shu liganing klublari; har bosqichda
bir qadam ortga qaytaradigan "Orqaga" tugmasi bor. Tugmalar pastki klaviaturada turadi,
shuning uchun bosilgan tugma oddiy matnli xabar bo'lib keladi va find_club uni klub nomiga
qarab topadi.
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from golli.bot.views import club_label
from golli.competitions import COMPETITIONS
from golli.db.models import Team
from golli.i18n import Translator
from golli.services.team_names import TeamNames

COLUMNS = 2
# Tanlangan klub tugmasi shu belgi bilan boshlanadi.
SELECTED_MARK = "✅ "


def _club_lines(teams: list[Team], t: Translator, names: TeamNames) -> list[str]:
    return [f"• {club_label(team.name, team.emoji_id, t, names)}" for team in teams]


def root_text(favorites: list[Team], t: Translator, names: TeamNames) -> str:
    lines = [t("favorites-title"), ""]
    if favorites:
        lines += [t("favorites-current"), *_club_lines(favorites, t, names)]
    else:
        lines.append(t("favorites-empty"))
    lines += ["", t("favorites-hint")]
    return "\n".join(lines)


def summary_text(favorites: list[Team], t: Translator, names: TeamNames) -> str:
    """Birinchi tanishuvdagi klub tanlash tugagach ko'rsatiladigan yakun."""
    if not favorites:
        return t("favorites-none-saved")
    lines = [t("favorites-saved"), *_club_lines(favorites, t, names)]
    return "\n".join([*lines, "", t("favorites-saved-note")])


def _keyboard(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def _in_rows(buttons: list[KeyboardButton]) -> list[list[KeyboardButton]]:
    return [buttons[index : index + COLUMNS] for index in range(0, len(buttons), COLUMNS)]


def leagues_keyboard(t: Translator) -> ReplyKeyboardMarkup:
    leagues = [KeyboardButton(text=t(f"competition-{code}")) for code in COMPETITIONS]
    # Birinchi liga nomi uzun ("Chempionlar ligasi"), shuning uchun u alohida qatorda.
    return _keyboard(
        [
            leagues[:1],
            *_in_rows(leagues[1:]),
            [KeyboardButton(text=t("menu-back"))],
        ]
    )


def sort_teams(teams: list[Team], t: Translator, names: TeamNames) -> list[Team]:
    """Foydalanuvchi tilidagi nom bo'yicha alifbo tartibida."""
    return sorted(teams, key=lambda team: names.get(team.name, t.locale).casefold())


def clubs_text(competition: str, has_teams: bool, t: Translator) -> str:
    title = f"<b>{t(f'competition-{competition}')}</b>"
    return f"{title}\n\n{t('favorites-pick' if has_teams else 'favorites-no-teams')}"


def clubs_keyboard(
    teams: list[Team], selected: set[int], t: Translator, names: TeamNames
) -> ReplyKeyboardMarkup:
    """Liganing barcha klublari (ro'yxat uzun bo'lsa, klaviatura aylantiriladi)."""
    clubs = [
        KeyboardButton(
            text=(SELECTED_MARK if team.id in selected else "") + names.get(team.name, t.locale),
            # Klub logotipi tugma matni oldida (emoji hali yaratilmagan bo'lsa — None).
            icon_custom_emoji_id=team.emoji_id,
        )
        for team in teams
    ]
    return _keyboard([*_in_rows(clubs), [KeyboardButton(text=t("menu-back"))]])


def find_club(text: str, teams: list[Team], t: Translator, names: TeamNames) -> Team | None:
    """Bosilgan tugma matni bo'yicha klub; bunday klub bo'lmasa None."""
    wanted = text.removeprefix(SELECTED_MARK).strip()
    return next((team for team in teams if names.get(team.name, t.locale) == wanted), None)
