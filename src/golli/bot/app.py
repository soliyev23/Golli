from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from golli.bot.handlers import (
    favorites,
    language,
    matches,
    membership,
    menu,
    settings,
    start,
    tournaments,
)
from golli.bot.middlewares import DbSessionMiddleware, UserMiddleware
from golli.i18n import I18n
from golli.services.schedule import ScheduleCache
from golli.services.team_names import TeamNames


def create_dispatcher(
    storage: BaseStorage,
    session_factory: async_sessionmaker[AsyncSession],
    i18n: I18n,
    schedule: ScheduleCache,
    names: TeamNames,
    new_user_alert_chat_id: int | None = None,
) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    # Handler va filtrlar bularni parametr nomi bo'yicha oladi.
    dispatcher["i18n"] = i18n
    dispatcher["schedule"] = schedule
    dispatcher["names"] = names

    # Tartib muhim: avval sessiya ochiladi, keyin foydalanuvchi shu sessiyada topiladi.
    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    dispatcher.update.outer_middleware(UserMiddleware(i18n, new_user_alert_chat_id))

    # language birinchi: til tanlamagan foydalanuvchining har qanday xabari o'sha yerda ushlanadi.
    # menu oxirida: unda boshqa handler ushlamagan xabarlar uchun javob bor.
    dispatcher.include_routers(
        language.router,
        start.router,
        membership.router,
        matches.router,
        settings.router,
        tournaments.router,
        favorites.router,
        menu.router,
    )
    return dispatcher
