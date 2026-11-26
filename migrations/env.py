import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from golli.config import Settings
from golli.db import models  # noqa: F401  (modellar Base.metadata ga yozilishi uchun)
from golli.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_url() -> URL:
    # Testlar manzilni config.attributes orqali beradi, qolgan holatda .env dan olinadi.
    return config.attributes.get("database_url") or Settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(get_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
