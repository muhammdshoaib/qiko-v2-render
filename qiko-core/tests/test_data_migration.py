from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.migration import parity_count, upsert_users


async def _sm(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


LEGACY = [
    {"id": "u1", "email": "A@qiko.ai", "password_hash": "h1", "role": "owner", "tenant_id": "acme"},
    {"id": "u2", "email": "b@qiko.ai", "password_hash": "h2"},
]


async def test_migration_is_idempotent_and_reports(tmp_path):
    sm = await _sm(tmp_path / "m.db")

    first = await upsert_users(sm, LEGACY)
    assert first.inserted == 2 and first.updated == 0
    assert await parity_count(sm) == 2  # parity with source count

    # Re-run: no duplicates, all treated as updates.
    second = await upsert_users(sm, LEGACY)
    assert second.inserted == 0 and second.updated == 2
    assert await parity_count(sm) == 2


async def test_dry_run_writes_nothing(tmp_path):
    sm = await _sm(tmp_path / "d.db")
    report = await upsert_users(sm, LEGACY, dry_run=True)
    assert report.inserted == 2
    assert await parity_count(sm) == 0  # nothing written
