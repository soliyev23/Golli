"""Sevimli klublar bo'limining matn va tugmalari."""

from html import escape
from math import ceil

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from golli.bot.callbacks import FavoriteListCallback, FavoritesCallback, FavoriteToggleCallback
from golli.competitions import COMPETITIONS
from golli.db.models import Team
from golli.i18n import Translator
from golli.services.team_names import TeamNames

# Bitta sahifadagi klublar: ikki ustun x o'n qator. APL va La Liga bitta sahifaga sig'adi.
PAGE_SIZE = 20
COLUMNS = 2


def root_text(favorites: list[Team], t: Translator, names: TeamNames) -> str:
    lines = [t("favorites-title"), ""]
    if favorites:
        lines.append(t("favorites-current"))
        lines += [f"• {escape(names.get(team.name, t.locale), quote=False)}" for team in favorites]
    else:
        lines.append(t("favorites-empty"))
    lines += ["", t("favorites-hint")]
    return "\n".join(lines)


def root_keyboard(t: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(f"competition-{competition}"),
                    callback_data=FavoriteListCallback(competition=competition).pack(),
                )
            ]
            for competition in COMPETITIONS
        ]
    )


def sort_teams(teams: list[Team], t: Translator, names: TeamNames) -> list[Team]:
    """Foydalanuvchi tilidagi nom bo'yicha alifbo tartibida."""
    return sorted(teams, key=lambda team: names.get(team.name, t.locale).casefold())


def page_count(teams: list[Team]) -> int:
    return max(1, ceil(len(teams) / PAGE_SIZE))


def list_text(competition: str, page: int, pages: int, has_teams: bool, t: Translator) -> str:
    title = f"<b>{t(f'competition-{competition}')}</b>"
    if pages > 1:
        title += f" · {page + 1}/{pages}"
    return f"{title}\n\n{t('favorites-pick' if has_teams else 'favorites-no-teams')}"


def list_keyboard(
    competition: str,
    teams: list[Team],
    selected: set[int],
    page: int,
    t: Translator,
    names: TeamNames,
) -> InlineKeyboardMarkup:
    """`teams` — tartiblangan to'liq ro'yxat; shundan `page`-sahifa chiziladi."""
    visible = teams[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    buttons = [
        InlineKeyboardButton(
            text=("✅ " if team.id in selected else "") + names.get(team.name, t.locale),
            callback_data=FavoriteToggleCallback(
                competition=competition, page=page, team_id=team.id
            ).pack(),
        )
        for team in visible
    ]
    rows = [buttons[index : index + COLUMNS] for index in range(0, len(buttons), COLUMNS)]

    def page_button(text: str, target: int) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text,
            callback_data=FavoriteListCallback(competition=competition, page=target).pack(),
        )

    pager = []
    if page > 0:
        pager.append(page_button("◀️", page - 1))
    if page + 1 < page_count(teams):
        pager.append(page_button("▶️", page + 1))
    if pager:
        rows.append(pager)

    rows.append(
        [InlineKeyboardButton(text=t("favorites-back"), callback_data=FavoritesCallback().pack())]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
