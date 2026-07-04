from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.migration import (
    reconcile_user,
    upsert_agents,
    upsert_conversations,
    upsert_users,
    parity_count,
)
from app.db.models import Agent as AgentRow
from app.db.migration import count_rows


async def _sm(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


def test_reconcile_user_handles_both_legacy_shapes():
    # qiko-backend shape (user_name/passfield)
    a = reconcile_user({"id": "1", "user_name": "A@X.com", "passfield": "h1", "tenant_id": "t"})
    assert a["email"] == "a@x.com" and a["password_hash"] == "h1"
    # admin-backend shape (email/password)
    b = reconcile_user({"id": "2", "email": "B@X.com", "password": "h2"})
    assert b["email"] == "b@x.com" and b["password_hash"] == "h2" and b["role"] == "viewer"


async def test_users_migrate_from_mixed_shapes_idempotently(tmp_path):
    sm = await _sm(tmp_path / "u.db")
    legacy = [{"id": "1", "user_name": "a@x.com", "passfield": "h1", "tenant_id": "t"},
              {"id": "2", "email": "b@x.com", "password": "h2", "tenant_id": "t"}]
    first = await upsert_users(sm, legacy)
    assert (first.inserted, first.updated) == (2, 0)
    second = await upsert_users(sm, legacy)          # re-run: idempotent
    assert (second.inserted, second.updated) == (0, 2)
    assert await parity_count(sm) == 2


async def test_agents_and_conversations_migrate(tmp_path):
    sm = await _sm(tmp_path / "a.db")
    await upsert_agents(sm, [{"id": "ag1", "tenant_id": "t", "name": "IDG", "status": "ready"}])
    await upsert_conversations(sm, [{"id": "c1", "tenant_id": "t", "user_id": "u1", "agent_id": "ag1"}])
    assert await count_rows(sm, AgentRow) == 1
    # dry-run writes nothing
    rep = await upsert_agents(sm, [{"id": "ag2", "tenant_id": "t", "name": "New"}], dry_run=True)
    assert rep.inserted == 1 and await count_rows(sm, AgentRow) == 1
