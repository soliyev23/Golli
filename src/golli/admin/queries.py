"""Admin panel uchun bazadan o'qish: KPI, foydalanuvchilar jadvali, havolalar statistikasi."""

import secrets
import string
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from golli.db.models import Favorite, InviteLink, Team, User

# Ulashish havolasi manbalari: kod -> panelda ko'rinadigan nom.
SOURCES: dict[str, str] = {"telegram": "Telegram", "instagram": "Instagram", "other": "Boshqa"}
ORGANIC = "organic"
ACTIVE_WINDOW = timedelta(hours=24)
PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class Kpi:
    total: int
    active_24h: int
    from_telegram: int
    from_instagram: int
    new_today: int
    blocked: int


@dataclass(frozen=True, slots=True)
class UserRow:
    id: int
    first_name: str | None
    last_name: str | None
    username: str | None
    lang: str | None
    language_code: str | None
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None
    link_name: str | None
    link_source: str | None
    favorites: tuple[str, ...]

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part) or "—"


@dataclass(frozen=True, slots=True)
class UserFilter:
    query: str = ""
    # "new" — oxirgi qo'shilganlar tepada; "active" — oxirgi faollar tepada.
    sort: str = "new"
    # "all", "active" (24 soat ichida), "blocked"
    status: str = "all"
    # "" — hammasi; "telegram"/"instagram"/"other"/"organic"; yoki "link:<id>"
    source: str = ""


@dataclass(frozen=True, slots=True)
class LinkStats:
    id: int
    code: str
    name: str
    source: str
    created_at: datetime
    users: int
    active_24h: int


def _day_start(day: date, tz: tzinfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz)


async def load_kpi(session: AsyncSession, now: datetime, tz: tzinfo) -> Kpi:
    today = _day_start(now.astimezone(tz).date(), tz)
    active_since = now - ACTIVE_WINDOW
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(User.last_seen_at >= active_since),
                func.count().filter(InviteLink.source == "telegram"),
                func.count().filter(InviteLink.source == "instagram"),
                func.count().filter(User.created_at >= today),
                func.count().filter(User.is_active.is_(False)),
            )
            .select_from(User)
            .outerjoin(InviteLink, InviteLink.id == User.invite_link_id)
        )
    ).one()
    return Kpi(*row)


def _filtered(query: Select, filters: UserFilter, now: datetime) -> Select:
    if filters.query:
        text = filters.query.strip().lstrip("@")
        conditions = [
            User.first_name.ilike(f"%{text}%"),
            User.last_name.ilike(f"%{text}%"),
            User.username.ilike(f"%{text}%"),
        ]
        if text.isdigit():
            conditions.append(User.id == int(text))
        query = query.where(or_(*conditions))
    if filters.status == "active":
        query = query.where(User.last_seen_at >= now - ACTIVE_WINDOW)
    elif filters.status == "blocked":
        query = query.where(User.is_active.is_(False))
    if filters.source == ORGANIC:
        query = query.where(User.invite_link_id.is_(None))
    elif filters.source in SOURCES:
        query = query.where(InviteLink.source == filters.source)
    elif filters.source.startswith("link:") and filters.source[5:].isdigit():
        query = query.where(User.invite_link_id == int(filters.source[5:]))
    return query


async def load_users(
    session: AsyncSession,
    filters: UserFilter,
    now: datetime,
    page: int = 1,
    page_size: int = PAGE_SIZE,
) -> tuple[list[UserRow], int]:
    """Filtrlangan foydalanuvchilar sahifasi va umumiy soni."""
    base = select(User, InviteLink.name, InviteLink.source).outerjoin(
        InviteLink, InviteLink.id == User.invite_link_id
    )
    base = _filtered(base, filters, now)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))

    if filters.sort == "active":
        order = (User.last_seen_at.desc().nulls_last(), User.created_at.desc())
    else:
        order = (User.created_at.desc(), User.id.desc())
    rows = (
        await session.execute(base.order_by(*order).limit(page_size).offset((page - 1) * page_size))
    ).all()

    favorites = await _favorites(session, [user.id for user, *_ in rows])
    return [
        UserRow(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            lang=user.lang,
            language_code=user.language_code,
            is_active=user.is_active,
            created_at=user.created_at,
            last_seen_at=user.last_seen_at,
            link_name=link_name,
            link_source=link_source,
            favorites=favorites.get(user.id, ()),
        )
        for user, link_name, link_source in rows
    ], total or 0


async def _favorites(session: AsyncSession, user_ids: Sequence[int]) -> dict[int, tuple[str, ...]]:
    if not user_ids:
        return {}
    rows = await session.execute(
        select(Favorite.user_id, Team.name)
        .join(Team, Team.id == Favorite.team_id)
        .where(Favorite.user_id.in_(user_ids))
        .order_by(Favorite.created_at)
    )
    result: dict[int, list[str]] = {}
    for user_id, name in rows:
        result.setdefault(user_id, []).append(name)
    return {user_id: tuple(names) for user_id, names in result.items()}


async def new_users_by_day(
    session: AsyncSession, now: datetime, tz: tzinfo, days: int = 30
) -> list[tuple[date, int]]:
    """Oxirgi `days` kunda har kuni qo'shilgan foydalanuvchilar (o'zbek vaqti bilan)."""
    today = now.astimezone(tz).date()
    first = today - timedelta(days=days - 1)
    local_day = func.date(func.timezone(str(tz), User.created_at))
    rows = await session.execute(
        select(local_day, func.count())
        .where(User.created_at >= _day_start(first, tz))
        .group_by(local_day)
    )
    counts = dict(rows.all())
    return [
        (first + timedelta(days=i), counts.get(first + timedelta(days=i), 0)) for i in range(days)
    ]


async def top_clubs(session: AsyncSession, limit: int = 10) -> list[tuple[str, int]]:
    rows = await session.execute(
        select(Team.name, func.count())
        .join(Favorite, Favorite.team_id == Team.id)
        .group_by(Team.name)
        .order_by(func.count().desc(), Team.name)
        .limit(limit)
    )
    return [(name, count) for name, count in rows]


async def languages(session: AsyncSession) -> list[tuple[str | None, int]]:
    rows = await session.execute(
        select(User.lang, func.count()).group_by(User.lang).order_by(func.count().desc())
    )
    return [(lang, count) for lang, count in rows]


async def load_links(session: AsyncSession, now: datetime) -> list[LinkStats]:
    active_since = now - ACTIVE_WINDOW
    rows = await session.execute(
        select(
            InviteLink,
            func.count(User.id),
            func.count(User.id).filter(User.last_seen_at >= active_since),
        )
        .outerjoin(User, User.invite_link_id == InviteLink.id)
        .group_by(InviteLink.id)
        .order_by(InviteLink.created_at.desc())
    )
    return [
        LinkStats(link.id, link.code, link.name, link.source, link.created_at, users, active)
        for link, users, active in rows
    ]


async def source_breakdown(session: AsyncSession) -> list[tuple[str, int]]:
    """Manbalar bo'yicha foydalanuvchilar: telegram, instagram, other, organic."""
    source = case((User.invite_link_id.is_(None), ORGANIC), else_=InviteLink.source)
    rows = await session.execute(
        select(source, func.count())
        .select_from(User)
        .outerjoin(InviteLink, and_(InviteLink.id == User.invite_link_id))
        .group_by(source)
        .order_by(func.count().desc())
    )
    return [(name, count) for name, count in rows]


def new_link_code(source: str) -> str:
    """Qisqa, taxmin qilib bo'lmaydigan kod: "ig-k3m9x2" kabi (Telegram start parametri)."""
    prefix = {"telegram": "tg", "instagram": "ig"}.get(source, "go")
    alphabet = string.ascii_lowercase + string.digits
    return f"{prefix}-{''.join(secrets.choice(alphabet) for _ in range(6))}"
