"""End-to-end data migration: legacy SQLite -> unified target, idempotent, via the CLI runner."""
import sqlite3

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.legacy_readers import read_sqlite_table
from app.db.migrate_cli import run_sqlite_migration
from app.db.migration import count_rows
from app.db.models import User as UserRow


def _legacy_db(path) -> str:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id TEXT, email TEXT, password_hash TEXT, tenant_id TEXT, role TEXT)")
    conn.executemany("INSERT INTO users VALUES (?,?,?,?,?)", [
        ("1", "a@x.com", "h1", "t", "owner"), ("2", "b@x.com", "h2", "t", "viewer")])
    conn.commit()
    conn.close()
    return str(path)


async def _target(path) -> async_sessionmaker:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


def test_read_sqlite_table_missing_is_empty(tmp_path):
    p = _legacy_db(tmp_path / "legacy.db")
    assert len(read_sqlite_table(p, "users")) == 2
    assert read_sqlite_table(p, "does_not_exist") == []


async def test_run_sqlite_migration_idempotent(tmp_path):
    legacy = _legacy_db(tmp_path / "legacy.db")
    sm = await _target(tmp_path / "target.db")
    first = await run_sqlite_migration(legacy, sm)
    assert first["users"] == {"inserted": 2, "updated": 0}
    assert await count_rows(sm, UserRow) == 2
    second = await run_sqlite_migration(legacy, sm)          # re-run
    assert second["users"] == {"inserted": 0, "updated": 2}  # idempotent
    dry = await run_sqlite_migration(legacy, sm, dry_run=True)
    assert dry["users"]["updated"] == 2 and await count_rows(sm, UserRow) == 2
