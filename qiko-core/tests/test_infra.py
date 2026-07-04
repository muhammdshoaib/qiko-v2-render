from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import build_engine, build_sessionmaker
from app.core.redis import build_redis


def test_build_engine_returns_async_engine():
    engine = build_engine("postgresql+asyncpg://u:p@localhost:5432/db")
    assert isinstance(engine, AsyncEngine)


def test_build_sessionmaker():
    engine = build_engine("postgresql+asyncpg://u:p@localhost:5432/db")
    sm = build_sessionmaker(engine)
    assert isinstance(sm, async_sessionmaker)
    # Producing a session (without connecting) yields an AsyncSession bound to our engine.
    session = sm()
    assert isinstance(session, AsyncSession)
    assert session.bind is engine


def test_build_redis():
    client = build_redis("redis://localhost:6379/0")
    assert client is not None
    assert hasattr(client, "get")
