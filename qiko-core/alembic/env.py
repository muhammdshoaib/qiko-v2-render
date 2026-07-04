"""Alembic environment. Migrations run synchronously (standard) even though the app is async;
the URL is derived from settings (async driver stripped) or overridden via ALEMBIC_URL."""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.db.models  # noqa: F401  (register models on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def _sync_url() -> str:
    override = os.environ.get("ALEMBIC_URL")
    if override:
        return override
    url = get_settings().database_url
    return url.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")


config.set_main_option("sqlalchemy.url", _sync_url())


def run_migrations_offline() -> None:
    context.configure(url=_sync_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
