from sqlalchemy import delete, func, select, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from golli.competitions import MAIN_STAGE_ROUND_PREFIX
from golli.db.models import Favorite, Match, Team


async def competition_teams(session: AsyncSession, competition: str) -> list[Team]:
    """Turnirning joriy (bazadagi eng so'nggi) mavsumi klublari."""
    latest_season = (
        select(func.max(Match.season)).where(Match.competition == competition).scalar_subquery()
    )
    conditions = [Match.competition == competition, Match.season == latest_season]
    prefix = MAIN_STAGE_ROUND_PREFIX.get(competition)
    if prefix is not None:
        conditions.append(Match.round.startswith(prefix, autoescape=True))

    team_ids = union(
        select(Match.home_team_id.label("team_id")).where(*conditions),
        select(Match.away_team_id.label("team_id")).where(*conditions),
    ).subquery()
    teams = await session.scalars(select(Team).where(Team.id.in_(select(team_ids.c.team_id))))
    return list(teams)


async def favorite_teams(session: AsyncSession, user_id: int) -> list[Team]:
    """Foydalanuvchi tanlagan klublar, tanlangan tartibida."""
    teams = await session.scalars(
        select(Team)
        .join(Favorite, Favorite.team_id == Team.id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at, Team.id)
    )
    return list(teams)


async def toggle_favorite(
    session: AsyncSession, user_id: int, team_id: int
) -> tuple[Team, bool] | None:
    """Klub tanlanmagan bo'lsa qo'shadi, tanlangan bo'lsa olib tashlaydi.

    Qaytaradi: (klub, endi tanlanganmi). Bunday klub bo'lmasa None.
    """
    team = await session.get(Team, team_id)
    if team is None:
        return None

    # Avval o'chirib ko'riladi, o'chmagan bo'lsa qo'shiladi: tugma ketma-ket ikki marta
    # bosilganda ham (so'rovlar parallel ishlaydi) takroriy qator xatosi chiqmaydi.
    removed = await session.execute(
        delete(Favorite)
        .where(Favorite.user_id == user_id, Favorite.team_id == team_id)
        .returning(Favorite.team_id)
    )
    if removed.first() is not None:
        return team, False
    await session.execute(
        insert(Favorite).values(user_id=user_id, team_id=team_id).on_conflict_do_nothing()
    )
    return team, True
