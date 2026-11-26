"""Fon vazifalari: provayderdan ma'lumot olib, bazaga yozish va keshni yangilash.

Worker har daqiqada tick() ni chaqiradi. API'ga so'rov faqat kerak bo'lganda ketadi:
  - mavsum taqvimi — kuniga bir marta (futbol kuni almashganda);
  - bugungi o'yinlar holati — faqat belgilangan nuqtalarda (poll_due ga qarang).
Bepul tarifda kuniga 100 ta so'rov bor, shuning uchun jadval ataylab siyrak.
"""

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, tzinfo

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from golli.competitions import COMPETITIONS
from golli.db.matches import has_unfinished, unfinished_kickoffs, upsert_matches
from golli.providers.base import FootballProvider, ProviderError
from golli.services.days import current_season, football_day
from golli.services.schedule import ScheduleCache

logger = logging.getLogger(__name__)

LAST_SEASON_SYNC_KEY = "golli:sync:season:last"

# Mavsum sinxronizatsiyasi xato bersa, shuncha vaqtdan keyin qayta uriniladi.
SEASON_RETRY_DELAY = timedelta(minutes=30)
# Qarovsiz qolgan (tugashi qayd etilmagan) o'yinlar uchun navbatdan tashqari
# sinxronizatsiya ko'pi bilan shuncha vaqtda bir marta. Oraliq uzun: provayder
# o'yin holatini o'zi yangilamayotgan bo'lsa, limit behuda sarflanmasin.
STALE_RESYNC_INTERVAL = timedelta(hours=12)
STALE_LOOKBACK = timedelta(days=3)

# O'yin boshlanganidan keyin shu vaqtgacha holati kuzatiladi; undan eskisini
# kunlik mavsum sinxronizatsiyasi tuzatadi.
LIVE_WINDOW = timedelta(hours=4)
# Tekshiruv nuqtalari: boshlanganini tasdiqlash va tanaffusdagi hisob.
CHECKPOINTS = (timedelta(minutes=10), timedelta(minutes=55))
# Shundan keyin o'yin tugashi kutiladi va tez-tez tekshiriladi.
ENDING_AFTER = timedelta(minutes=105)
ENDING_INTERVAL = timedelta(minutes=3)
# Qo'shimcha vaqt/penaltilar yoki provayder kechikishi: sekinroq tekshiriladi.
LATE_AFTER = timedelta(minutes=135)
LATE_INTERVAL = timedelta(minutes=5)


def poll_due(now: datetime, kickoffs: Iterable[datetime], last_poll: datetime | None) -> bool:
    """Tugamagan o'yinlari `kickoffs` da boshlangan turnirni hozir so'rash kerakmi?"""
    for kickoff in kickoffs:
        elapsed = now - kickoff
        if elapsed >= ENDING_AFTER:
            interval = ENDING_INTERVAL if elapsed < LATE_AFTER else LATE_INTERVAL
            if last_poll is None or now - last_poll >= interval:
                return True
        elif any(
            kickoff + checkpoint <= now and (last_poll is None or last_poll < kickoff + checkpoint)
            for checkpoint in CHECKPOINTS
        ):
            return True
    return False


class Syncer:
    def __init__(
        self,
        provider: FootballProvider,
        session_factory: async_sessionmaker[AsyncSession],
        schedule: ScheduleCache,
        redis: Redis,
        tz: tzinfo,
    ) -> None:
        self._provider = provider
        self._session_factory = session_factory
        self._schedule = schedule
        self._redis = redis
        self._tz = tz
        self._season_retry_after: datetime | None = None
        self._last_poll: dict[str, datetime] = {}
        self._cache_day = None

    async def tick(self, now: datetime | None = None) -> None:
        """Bitta aylanish. Bir vazifadagi xato qolganlarini to'xtatmaydi."""
        now = now or datetime.now(UTC)
        for name, step in (
            ("mavsum sinxronizatsiyasi", self.sync_season_if_due),
            ("jonli yangilash", self.refresh_live),
            ("kesh", self.rebuild_cache_if_day_changed),
        ):
            try:
                await step(now)
            except ProviderError as exc:
                logger.warning("%s: %s", name, exc)
            except Exception:
                logger.exception("%s: kutilmagan xato", name)

    # --- Mavsum taqvimi

    async def sync_season_if_due(self, now: datetime) -> None:
        if self._season_retry_after is not None and now < self._season_retry_after:
            return
        if not await self._season_sync_due(now):
            return
        try:
            await self.sync_season(now)
        except ProviderError:
            self._season_retry_after = now + SEASON_RETRY_DELAY
            raise

    async def _season_sync_due(self, now: datetime) -> bool:
        last = await self._last_season_sync()
        if last is None or football_day(last, self._tz) != football_day(now, self._tz):
            return True
        # Bugun sinxronlangan. Faqat qarovsiz qolgan o'yin bo'lsa qayta sinxronlanadi
        # (masalan, worker o'yin paytida o'chiq bo'lgan).
        return now - last >= STALE_RESYNC_INTERVAL and await self._has_stale_matches(now)

    async def sync_season(self, now: datetime) -> None:
        season = current_season(now)
        created = updated = 0
        for competition in COMPETITIONS:
            items = await self._provider.fetch_season(competition, season)
            async with self._session_factory.begin() as session:
                result = await upsert_matches(session, self._provider.name, items)
            created += result.created
            updated += result.updated
        await self._redis.set(LAST_SEASON_SYNC_KEY, now.isoformat())
        self._season_retry_after = None
        await self._rebuild_cache(now)
        logger.info(
            "Mavsum %s sinxronlandi: %s ta yangi, %s ta o'zgargan o'yin. Limit qoldig'i: %s",
            season,
            created,
            updated,
            getattr(self._provider, "quota_remaining", None),
        )

    async def _last_season_sync(self) -> datetime | None:
        raw = await self._redis.get(LAST_SEASON_SYNC_KEY)
        if raw is None:
            return None
        return datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw)

    async def _has_stale_matches(self, now: datetime) -> bool:
        async with self._session_factory() as session:
            return await has_unfinished(session, now - STALE_LOOKBACK, now - LIVE_WINDOW)

    # --- Bugungi o'yinlar holati

    async def refresh_live(self, now: datetime) -> None:
        async with self._session_factory() as session:
            candidates = await unfinished_kickoffs(session, now - LIVE_WINDOW, now)
        kickoffs_by_competition: dict[str, list[datetime]] = defaultdict(list)
        for competition, kickoff in candidates:
            kickoffs_by_competition[competition].append(kickoff)

        refreshed = False
        for competition, kickoffs in kickoffs_by_competition.items():
            if not poll_due(now, kickoffs, self._last_poll.get(competition)):
                continue
            # Vaqt so'rovdan oldin yoziladi: so'rov xato bersa ham keyingisi jadval bo'yicha ketadi.
            self._last_poll[competition] = now
            for day in sorted({kickoff.astimezone(UTC).date() for kickoff in kickoffs}):
                items = await self._provider.fetch_day(competition, day)
                async with self._session_factory.begin() as session:
                    result = await upsert_matches(session, self._provider.name, items)
                refreshed = True
                logger.info(
                    "%s %s yangilandi: %s ta o'yin o'zgardi. Limit qoldig'i: %s",
                    competition,
                    day,
                    result.updated,
                    getattr(self._provider, "quota_remaining", None),
                )
        if refreshed:
            await self._rebuild_cache(now)

    # --- Kesh

    async def rebuild_cache_if_day_changed(self, now: datetime) -> None:
        """Kun almashganda (va ishga tushganda) kesh oynasi suriladi, API'ga so'rovsiz."""
        if self._cache_day != self._schedule.today(now):
            await self._rebuild_cache(now)

    async def _rebuild_cache(self, now: datetime) -> None:
        await self._schedule.rebuild(now)
        self._cache_day = self._schedule.today(now)
