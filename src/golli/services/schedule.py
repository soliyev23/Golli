"""Kunlik o'yinlar ro'yxati: Redis'dagi tayyor nusxalar.

Worker har yangilanishdan keyin nusxalarni qayta quradi (rebuild). Bot faqat shu
nusxalardan o'qiydi; nusxa topilmasa (Redis tozalangan bo'lsa) bazadan olib, keshga
qo'yadi. Tashqi API'ga bu yerdan hech qachon murojaat qilinmaydi.
"""

from datetime import UTC, date, datetime, timedelta, tzinfo

from pydantic import BaseModel, ConfigDict, TypeAdapter
from redis.asyncio import Redis
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from golli.db.models import Match, Team
from golli.providers.base import MatchStatus
from golli.services.days import day_bounds, local_date

# Keshda turadigan kunlar: bugundan shuncha kun orqaga va oldinga. "Yaqin o'yinlar" va
# "Oxirgi o'yinlar" shu oynadan o'yin kunlarini qidiradi; oyna milliy terma jamoalar
# tanaffusidek (taxminan ikki hafta o'yinsiz) oraliqni qoplashi kerak.
PAST_DAYS = 14
FUTURE_DAYS = 14
# Nusxalar kamida kuniga bir marta qayta quriladi; TTL zaxira bilan olingan.
TTL = timedelta(hours=36)

MATCH_DAYS_KEY = "golli:match_days"


class DayMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    competition: str
    kickoff_at: datetime
    status: MatchStatus
    minute: int | None
    home_id: int
    home: str
    away_id: int
    away: str
    home_score: int | None
    away_score: int | None
    home_penalties: int | None
    away_penalties: int | None
    # Klub logotipi — Telegram maxsus emojisi identifikatori (bo'lmasa None).
    home_emoji: str | None = None
    away_emoji: str | None = None


_matches = TypeAdapter(list[DayMatch])
_days = TypeAdapter(list[date])


async def load_matches(session: AsyncSession, *conditions: ColumnElement[bool]) -> list[DayMatch]:
    """Shartlarga mos o'yinlar, klub nomlari bilan, boshlanish vaqti tartibida."""
    home, away = aliased(Team), aliased(Team)
    query = (
        select(Match, home.name, away.name, home.emoji_id, away.emoji_id)
        .join(home, Match.home_team_id == home.id)
        .join(away, Match.away_team_id == away.id)
        .where(*conditions)
        .order_by(Match.kickoff_at, Match.id)
    )
    return [
        DayMatch(
            id=match.id,
            competition=match.competition,
            kickoff_at=match.kickoff_at,
            status=MatchStatus(match.status),
            minute=match.minute,
            home_id=match.home_team_id,
            home=home_name,
            away_id=match.away_team_id,
            away=away_name,
            home_score=match.home_score,
            away_score=match.away_score,
            home_penalties=match.home_penalties,
            away_penalties=match.away_penalties,
            home_emoji=home_emoji,
            away_emoji=away_emoji,
        )
        for match, home_name, away_name, home_emoji, away_emoji in (
            await session.execute(query)
        ).all()
    ]


def _day_key(day: date) -> str:
    return f"golli:day:{day.isoformat()}"


class ScheduleCache:
    def __init__(
        self, redis: Redis, session_factory: async_sessionmaker[AsyncSession], tz: tzinfo
    ) -> None:
        self._redis = redis
        self._session_factory = session_factory
        self.tz = tz

    def today(self, now: datetime | None = None) -> date:
        return local_date(now or datetime.now(UTC), self.tz)

    def window(self, now: datetime | None = None) -> tuple[date, date]:
        today = self.today(now)
        return today - timedelta(days=PAST_DAYS), today + timedelta(days=FUTURE_DAYS)

    async def rebuild(self, now: datetime | None = None) -> None:
        """Oynadagi barcha kunlar nusxasini bazadan qayta quradi."""
        first, last = self.window(now)
        by_day: dict[date, list[DayMatch]] = {
            first + timedelta(days=offset): [] for offset in range((last - first).days + 1)
        }
        for match in await self._load(day_bounds(first, self.tz)[0], day_bounds(last, self.tz)[1]):
            by_day[local_date(match.kickoff_at, self.tz)].append(match)

        async with self._redis.pipeline(transaction=True) as pipe:
            for day, matches in by_day.items():
                pipe.set(_day_key(day), _matches.dump_json(matches), ex=TTL)
            match_days = [day for day, matches in by_day.items() if matches]
            pipe.set(MATCH_DAYS_KEY, _days.dump_json(match_days), ex=TTL)
            await pipe.execute()

    async def get_day(self, day: date) -> list[DayMatch]:
        raw = await self._redis.get(_day_key(day))
        if raw is not None:
            return _matches.validate_json(raw)
        matches = await self._load(*day_bounds(day, self.tz))
        await self._redis.set(_day_key(day), _matches.dump_json(matches), ex=TTL)
        return matches

    async def get_match_days(self, now: datetime | None = None) -> list[date]:
        """Oynadagi o'yin bor kunlar, o'sish tartibida."""
        raw = await self._redis.get(MATCH_DAYS_KEY)
        if raw is None:
            await self.rebuild(now)
            raw = await self._redis.get(MATCH_DAYS_KEY)
        return _days.validate_json(raw)

    async def _load(self, start: datetime, end: datetime) -> list[DayMatch]:
        async with self._session_factory() as session:
            return await load_matches(session, Match.kickoff_at >= start, Match.kickoff_at < end)
