"""Async SQLAlchemy engine and session factory (SQLAlchemy 2.0 async style only)."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def build_engine(database_url: str | None = None) -> AsyncEngine:
    """Create the async engine. Does not connect until first use, so this is unit-testable."""
    url = database_url or get_settings().database_url
    return create_async_engine(url, pool_pre_ping=True, future=True)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
