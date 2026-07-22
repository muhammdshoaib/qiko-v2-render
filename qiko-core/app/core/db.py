"""SQLAlchemy engine and session factories.

The app is async end-to-end (async engine + async_sessionmaker) for every store behind an async
route. The billing lifecycle + admin Customers console, however, are reached through synchronous
`def` route handlers (which FastAPI runs in a worker threadpool), and their in-memory services
expose a synchronous interface. Their durable Postgres-backed replacements therefore use a plain
synchronous engine (build_sync_engine / build_sync_sessionmaker) so a blocking DB call is safe in
that threadpool -- see app.db.sync_stores.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(database_url: str | None = None) -> AsyncEngine:
    """Create the async engine. Does not connect until first use, so this is unit-testable."""
    url = database_url or get_settings().database_url
    return create_async_engine(url, pool_pre_ping=True, future=True)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def to_sync_url(database_url: str) -> str:
    """Map the async DATABASE_URL to its synchronous-driver equivalent (same as alembic/env.py):
    asyncpg -> psycopg (both installed), aiosqlite -> the stdlib sqlite driver."""
    return database_url.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")


def build_sync_engine(database_url: str | None = None) -> Engine:
    """Create the synchronous engine used by the billing + admin-customers stores. Lazy connect,
    so this is unit-testable and cheap to build alongside the async engine."""
    url = to_sync_url(database_url or get_settings().database_url)
    return create_engine(url, pool_pre_ping=True, future=True)


def build_sync_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, class_=Session, expire_on_commit=False)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:  # pragma: no cover - exercised only with a live DB
        _engine = build_engine()
        _sessionmaker = build_sessionmaker(_engine)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:  # pragma: no cover - needs a live DB
    async with _get_sessionmaker()() as session:
        yield session
