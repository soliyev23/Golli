"""Eslatmalar: rejalash (navbatga qo'yish) va yuborish.

Uch turdagi xabar bor, hammasi foydalanuvchining sevimli klublari bo'yicha:
  - ertalabki: soat 07:00 da bitta xabar (bir nechta klub bo'lsa ham) — shu kungi va
    shu kechasi, ertasi 06:00 gacha boshlanadigan o'yinlar haqida;
  - o'yin oldidan: boshlanishiga 1 soat qolganda;
  - natija: o'yin tugagach (tunda ovozsiz).

ReminderPlanner xabarlarni notifications jadvaliga qo'yadi, Sender ularni Telegram
limitiga mos tezlikda yuboradi. Ikkalasi ham tashqi futbol API'siga murojaat qilmaydi.
"""

import asyncio
import contextlib
import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InputRichMessage
from redis.asyncio import Redis
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from golli.bot import rich_view
from golli.bot.notification_view import (
    morning_days,
    render_morning,
    render_pre_match,
    render_result,
)
from golli.db.models import Match, Notification
from golli.db.notifications import (
    FAILED,
    KIND_MORNING,
    KIND_PRE_MATCH,
    KIND_RESULT,
    PENDING,
    SENT,
    SKIPPED,
    deactivate_users,
    due_notifications,
    enqueue_morning,
    enqueue_pre_match,
    enqueue_results,
    favorite_team_ids,
)
from golli.i18n import I18n
from golli.providers.base import MatchStatus
from golli.services.days import day_bounds, local_date
from golli.services.schedule import DayMatch, load_matches
from golli.services.team_names import TeamNames

logger = logging.getLogger(__name__)

# --- Rejalash

# Ertalabki xabar shu soatda yuboriladi. Worker shu paytda ishlamagan bo'lsa,
# MORNING_DEADLINE_HOUR gacha yuboradi; undan keyin "ertalabki" xabar ma'nosini yo'qotadi.
MORNING_HOUR = 7
MORNING_DEADLINE_HOUR = 12
# Ertalabki xabar ertasi kuni shu soatgacha boshlanadigan o'yinlarni ham qamraydi:
# yarim tundan keyingi o'yin o'z sanasining ertalabigacha tugab bo'ladi, shuning uchun
# u haqda bir kun oldin ertalab xabar beriladi (ro'yxatda o'z sanasi bilan ko'rsatiladi).
NIGHT_END_HOUR = 6
PRE_MATCH_LEAD = timedelta(hours=1)
# Boshlanganiga shundan ko'p vaqt o'tgan o'yin natijasi yuborilmaydi (eskirgan xabar).
RESULT_MAX_AGE = timedelta(hours=6)

LAST_MORNING_KEY = "golli:notify:morning:last"

# --- Yuborish

# Telegram umumiy limiti sekundiga taxminan 30 xabar; zaxira bilan 25.
BATCH_SIZE = 25
BATCH_INTERVAL = 1.0
IDLE_SLEEP = 3.0
MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(seconds=30)
# Shu oraliqda (bot vaqt mintaqasida) natija xabari ovozsiz yuboriladi.
QUIET_FROM_HOUR = 23
QUIET_UNTIL_HOUR = 8


def morning_horizon(day: date, tz: tzinfo) -> datetime:
    """`day` kungi ertalabki xabar shu paytgacha boshlanadigan o'yinlarni qamraydi."""
    return day_bounds(day, tz)[1] + timedelta(hours=NIGHT_END_HOUR)


class ReminderPlanner:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], redis: Redis, tz: tzinfo
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._tz = tz

    async def plan(self, now: datetime) -> None:
        await self._plan_morning(now)
        async with self._session_factory.begin() as session:
            pre = await enqueue_pre_match(session, now, PRE_MATCH_LEAD)
            results = await enqueue_results(session, now, RESULT_MAX_AGE)
        if pre or results:
            logger.info("Navbatga qo'yildi: o'yin oldidan %s ta, natija %s ta", pre, results)

    async def _plan_morning(self, now: datetime) -> None:
        local = now.astimezone(self._tz)
        if not MORNING_HOUR <= local.hour < MORNING_DEADLINE_HOUR:
            return
        day = local_date(now, self._tz)
        last = await self._redis.get(LAST_MORNING_KEY)
        if last is not None and last.decode() == day.isoformat():
            return
        async with self._session_factory.begin() as session:
            count = await enqueue_morning(session, day, now, morning_horizon(day, self._tz))
        await self._redis.set(LAST_MORNING_KEY, day.isoformat())
        logger.info("Ertalabki xabar (%s): %s ta foydalanuvchiga navbatga qo'yildi", day, count)


@dataclass(slots=True)
class _Outcome:
    notification_id: int
    user_id: int
    status: str
    error: str | None = None
    retry_after: float = 0.0
    transient: bool = False
    deactivate_user: bool = False


class Sender:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        i18n: I18n,
        names: TeamNames,
        tz: tzinfo,
    ) -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._i18n = i18n
        self._names = names
        self._tz = tz

    async def run(self, stop: asyncio.Event) -> None:
        """To'xtatish signaligacha navbatni bo'shatib turadi."""
        while not stop.is_set():
            started = time.monotonic()
            try:
                processed, pause = await self.process_batch()
            except Exception:
                logger.exception("Yuborishda kutilmagan xato")
                processed, pause = 0, 0.0
            if pause:
                delay = pause
            elif processed:
                delay = max(0.0, BATCH_INTERVAL - (time.monotonic() - started))
            else:
                delay = IDLE_SLEEP
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)

    async def process_batch(self, now: datetime | None = None) -> tuple[int, float]:
        """Navbatdan bitta to'plamni yuboradi.

        Qaytaradi: (ko'rib chiqilgan xabarlar soni, Telegram so'ragan kutish vaqti sekundda).
        """
        now = now or datetime.now(UTC)
        async with self._session_factory() as session:
            batch = self._one_per_user(await due_notifications(session, now, BATCH_SIZE * 4))
            if not batch:
                return 0, 0.0
            prepared = await self._prepare(session, batch, now)

        outcomes = await asyncio.gather(*(self._deliver(*item) for item in prepared))
        await self._record(outcomes, now)
        return len(batch), max(outcome.retry_after for outcome in outcomes)

    @staticmethod
    def _one_per_user(
        due: list[tuple[Notification, str | None]],
    ) -> list[tuple[Notification, str | None]]:
        # Bir chatga sekundiga bittadan ortiq xabar yubormaslik uchun: to'plamda har bir
        # foydalanuvchidan bitta xabar, qolganlari keyingi to'plamda ketadi.
        batch: dict[int, tuple[Notification, str | None]] = {}
        for notification, lang in due:
            batch.setdefault(notification.user_id, (notification, lang))
            if len(batch) == BATCH_SIZE:
                break
        return list(batch.values())

    async def _prepare(
        self, session: AsyncSession, batch: list[tuple[Notification, str | None]], now: datetime
    ) -> list[tuple[Notification, str | None, bool, InputRichMessage | None]]:
        """Har bir xabar uchun (xabar, matn yoki None, ovozsizmi, jadvalli ko'rinishi).

        Matn None bo'lsa, xabar yuborilmaydi. Jadvalli ko'rinish faqat ertalabki xabarda bor;
        Telegram uni qabul qilmasa, o'rniga matn yuboriladi.
        """
        match_ids = {n.match_id for n, _ in batch if n.match_id is not None}
        matches = (
            {match.id: match for match in await load_matches(session, Match.id.in_(match_ids))}
            if match_ids
            else {}
        )
        quiet = not QUIET_UNTIL_HOUR <= now.astimezone(self._tz).hour < QUIET_FROM_HOUR

        prepared = []
        for notification, lang in batch:
            t = self._i18n.translator(lang)
            text: str | None = None
            rich: InputRichMessage | None = None
            silent = False
            match = matches.get(notification.match_id)
            if notification.kind == KIND_PRE_MATCH:
                # O'yin ko'chirilgan yoki allaqachon boshlangan bo'lsa, eslatma eskirgan.
                if match and match.status is MatchStatus.SCHEDULED and match.kickoff_at > now:
                    text = render_pre_match(match, now, t, self._names, self._tz)
            elif notification.kind == KIND_RESULT:
                if (
                    match
                    and match.status is MatchStatus.FINISHED
                    and now - match.kickoff_at <= RESULT_MAX_AGE + timedelta(hours=2)
                ):
                    text = render_result(match, t, self._names)
                    silent = quiet
            elif notification.kind == KIND_MORNING:
                coming = await self._favorite_matches_ahead(session, notification, now)
                if coming:
                    text = render_morning(notification.day, coming, now, t, self._names, self._tz)
                    rich = rich_view.morning_message(
                        morning_days(coming, self._tz),
                        today=notification.day,
                        now=now,
                        t=t,
                        names=self._names,
                        tz=self._tz,
                    )
            prepared.append((notification, text, silent, rich))
        return prepared

    async def _favorite_matches_ahead(
        self, session: AsyncSession, notification: Notification, now: datetime
    ) -> list[DayMatch]:
        if notification.day != local_date(now, self._tz):
            return []
        team_ids = await favorite_team_ids(session, notification.user_id)
        return await load_matches(
            session,
            or_(Match.home_team_id.in_(team_ids), Match.away_team_id.in_(team_ids)),
            Match.status == MatchStatus.SCHEDULED.value,
            Match.kickoff_at > now,
            Match.kickoff_at < morning_horizon(notification.day, self._tz),
        )

    async def _send(
        self, user_id: int, text: str, silent: bool, rich: InputRichMessage | None
    ) -> None:
        if rich is not None:
            try:
                await self._bot.send_rich_message(user_id, rich, disable_notification=silent)
                return
            except TelegramBadRequest as exc:
                logger.warning("Jadvalli xabar qabul qilinmadi, oddiy matn yuboriladi: %s", exc)
        await self._bot.send_message(user_id, text, disable_notification=silent)

    async def _deliver(
        self,
        notification: Notification,
        text: str | None,
        silent: bool,
        rich: InputRichMessage | None = None,
    ) -> _Outcome:
        outcome = _Outcome(notification.id, notification.user_id, SENT)
        if text is None:
            outcome.status = SKIPPED
            return outcome
        try:
            await self._send(notification.user_id, text, silent, rich)
        except TelegramRetryAfter as exc:
            # Limitdan oshildi: xabar navbatda qoladi, Telegram aytgan vaqtcha kutiladi.
            outcome.status, outcome.retry_after = PENDING, float(exc.retry_after)
        except TelegramForbiddenError as exc:
            # Foydalanuvchi botni bloklagan yoki hisobini o'chirgan.
            outcome.status, outcome.error, outcome.deactivate_user = FAILED, exc.message, True
        except TelegramBadRequest as exc:
            outcome.status, outcome.error = FAILED, exc.message
        except TelegramAPIError as exc:
            # Tarmoq yoki Telegram serveri xatosi: keyinroq qayta uriniladi.
            outcome.status, outcome.error, outcome.transient = PENDING, exc.message, True
        return outcome

    async def _record(self, outcomes: list[_Outcome], now: datetime) -> None:
        async with self._session_factory.begin() as session:
            for outcome in outcomes:
                notification = await session.get(Notification, outcome.notification_id)
                if notification is None:
                    continue
                notification.error = outcome.error and outcome.error[:255]
                if outcome.transient:
                    notification.attempts += 1
                    if notification.attempts >= MAX_ATTEMPTS:
                        notification.status = FAILED
                    else:
                        notification.send_after = now + RETRY_DELAY * notification.attempts
                    continue
                notification.status = outcome.status
                if outcome.status == SENT:
                    notification.sent_at = now
                elif outcome.retry_after:
                    notification.send_after = now + timedelta(seconds=outcome.retry_after)
            await deactivate_users(
                session, {outcome.user_id for outcome in outcomes if outcome.deactivate_user}
            )

        counts = Counter(outcome.status for outcome in outcomes if not outcome.transient)
        errors = [outcome.error for outcome in outcomes if outcome.error]
        logger.info(
            "Xabarlar: %s ta yuborildi, %s ta eskirgani uchun tashlab ketildi, %s ta xato%s",
            counts[SENT],
            counts[SKIPPED],
            len(errors),
            f" (masalan: {errors[0]})" if errors else "",
        )
