import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlAgentStore
from app.modules.agents.service import Agent


async def _sm(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_agent_store_crud_and_tenant_scope(tmp_path):
    store = SqlAgentStore(await _sm(tmp_path / "a.db"))
    await store.add(Agent(id="a1", tenant="acme", name="IDG"))
    await store.add(Agent(id="a2", tenant="beta", name="Theirs"))
    assert [a.id for a in await store.list("acme")] == ["a1"]
    assert await store.count("acme") == 1
    ready = await store.mark_ready("acme", "a1")
    assert ready.status == "ready"
    assert (await store.list("acme"))[0].status == "ready"


async def test_agent_store_get_is_tenant_scoped(tmp_path):
    store = SqlAgentStore(await _sm(tmp_path / "c.db"))
    await store.add(Agent(id="a1", tenant="acme", name="IDG"))
    assert (await store.get("acme", "a1")).name == "IDG"
    assert await store.get("beta", "a1") is None    # not beta's agent
    assert await store.get("acme", "missing") is None


async def test_agent_store_mark_ready_cross_tenant_blocked(tmp_path):
    store = SqlAgentStore(await _sm(tmp_path / "b.db"))
    await store.add(Agent(id="a1", tenant="acme", name="IDG"))
    with pytest.raises(KeyError):
        await store.mark_ready("beta", "a1")   # not beta's agent
