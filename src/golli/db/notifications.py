"""Eslatmalar navbati: xabarlarni navbatga qo'yish va navbatdan o'qish."""

from datetime import date, datetime, timedelta

from sqlalchemy import Date, DateTime, Integer, String, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from golli.db.models import Favorite, Match, Notification, User
from golli.providers.base import MatchStatus

KIND_MORNING = "morning"
KIND_PRE_MATCH = "pre_match"
KIND_RESULT = "result"

PENDING = "pending"
SENT = "sent"
FAILED = "failed"
SKIPPED = "skipped"


async def _enqueue(
    session: AsyncSession,
    user_ids,
    kind: str,
    dedupe_key: str,
    now: datetime,
    *,
    match_id: int | None = None,
    day: date | None = None,
) -> int:
    """`user_ids` so'rovi qaytargan har bir foydalanuvchiga bittadan xabar qo'yadi.

    Avval qo'yilgan bo'lsa (user_id, dedupe_key) takrorlanmaydi. Qo'shilganlar sonini qaytaradi.
    Yuborish vaqti — rejalovchining `now` vaqti (baza soati emas): ikkalasi bir xil soatga tayansin.
    """
    users = user_ids.subquery()
    rows = select(
        users.c.user_id,
        literal(kind, String),
        literal(match_id, Integer),
        literal(day, Date),
        literal(dedupe_key, String),
        literal(now, DateTime(timezone=True)),
    )
    result = await session.execute(
        insert(Notification)
        .from_select(["user_id", "kind", "match_id", "day", "dedupe_key", "send_after"], rows)
        .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
    )
    return result.rowcount


def _active_fans():
    """Faol foydalanuvchilarning sevimlilari: (user_id, team_id)."""
    return select(Favorite.user_id).join(User, User.id == Favorite.user_id).where(User.is_active)


async def enqueue_morning(session: AsyncSession, day: date, now: datetime, until: datetime) -> int:
    """Sevimli klubi `until` gacha o'ynaydigan muxlislarga `day` kuni uchun bittadan xabar."""
    fans = (
        _active_fans()
        .join(
            Match,
            or_(Match.home_team_id == Favorite.team_id, Match.away_team_id == Favorite.team_id),
        )
        .where(
            Match.status == MatchStatus.SCHEDULED.value,
            Match.kickoff_at > now,
            Match.kickoff_at < until,
        )
        .distinct()
    )
    return await _enqueue(session, fans, KIND_MORNING, f"morning:{day.isoformat()}", now, day=day)


async def _enqueue_for_match(
    session: AsyncSession, match: Match, kind: str, prefix: str, now: datetime
) -> int:
    # DISTINCT: ikkala jamoa ham sevimli bo'lsa, baribir bitta xabar.
    fans = (
        _active_fans()
        .where(Favorite.team_id.in_((match.home_team_id, match.away_team_id)))
        .distinct()
    )
    return await _enqueue(session, fans, kind, f"{prefix}:{match.id}", now, match_id=match.id)


async def enqueue_pre_match(session: AsyncSession, now: datetime, lead: timedelta) -> int:
    """`lead` vaqt ichida boshlanadigan o'yinlar muxlislariga "o'yin oldidan" xabari."""
    matches = await session.scalars(
        select(Match).where(
            Match.status == MatchStatus.SCHEDULED.value,
            Match.pre_notified_at.is_(None),
            Match.kickoff_at > now,
            Match.kickoff_at <= now + lead,
        )
    )
    total = 0
    for match in matches:
        total += await _enqueue_for_match(session, match, KIND_PRE_MATCH, "pre", now)
        match.pre_notified_at = now
    return total


async def enqueue_results(session: AsyncSession, now: datetime, max_age: timedelta) -> int:
    """Hozirgina tugagan o'yinlar muxlislariga natija xabari.

    `max_age` dan oldin boshlangan o'yinlar natijasi yuborilmaydi: worker uzoq to'xtab
    qolgan bo'lsa, eskirgan natijalar to'planib ketmasin.
    """
    matches = await session.scalars(
        select(Match).where(
            Match.status == MatchStatus.FINISHED.value,
            Match.result_notified_at.is_(None),
            Match.kickoff_at > now - max_age,
        )
    )
    total = 0
    for match in matches:
        total += await _enqueue_for_match(session, match, KIND_RESULT, "result", now)
        match.result_notified_at = now
    return total


async def due_notifications(
    session: AsyncSession, now: datetime, limit: int
) -> list[tuple[Notification, str | None]]:
    """Yuborish vaqti kelgan xabarlar va foydalanuvchi tili, navbat tartibida."""
    rows = await session.execute(
        select(Notification, User.lang)
        .join(User, User.id == Notification.user_id)
        .where(Notification.status == PENDING, Notification.send_after <= now)
        .order_by(Notification.id)
        .limit(limit)
    )
    return [(notification, lang) for notification, lang in rows]


async def favorite_team_ids(session: AsyncSession, user_id: int) -> list[int]:
    return list(await session.scalars(select(Favorite.team_id).where(Favorite.user_id == user_id)))


async def deactivate_users(session: AsyncSession, user_ids: set[int]) -> None:
    if user_ids:
        await session.execute(update(User).where(User.id.in_(user_ids)).values(is_active=False))
