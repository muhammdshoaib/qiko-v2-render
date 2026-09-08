import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Tenant
from app.db.stores import SqlAgentStore
from app.modules.agents.service import Agent, PlanLimitError

# These two modules each run Base.metadata.drop_all + create_all against the SAME test database,
# so under xdist they must never land on different workers at the same time: one would drop the
# other's tables mid-test. Same group name in both files keeps them on one worker, which also
# serialises them relative to each other.
pytestmark = pytest.mark.xdist_group("postgres_schema")



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


async def test_agent_enabled_transition_is_audited_and_idempotent(tmp_path):
    store = SqlAgentStore(await _sm(tmp_path / "enabled.db"))
    await store.add(Agent(id="a1", tenant="acme", name="IDG"))

    changed = await store.set_enabled(
        "acme", "a1", False, changed_by_email="admin.invalid", reason="  contract ended  "
    )
    unchanged = await store.set_enabled(
        "acme", "a1", False, changed_by_email="admin.invalid", reason="duplicate"
    )
    audit = await store.list_state_audit("acme")

    assert changed.enabled is False
    assert unchanged.enabled is False
    assert len(audit) == 1
    assert audit[0].previous_enabled is True
    assert audit[0].enabled is False
    assert audit[0].reason == "contract ended"
    assert audit[0].changed_by_email == "admin.invalid"


async def test_add_with_limit_counts_disabled_and_archived_and_supports_unlimited(tmp_path):
    sessionmaker = await _sm(tmp_path / "limit.db")
    async with sessionmaker() as session, session.begin():
        session.add(Tenant(id="acme", name="Acme"))
    store = SqlAgentStore(sessionmaker)
    await store.add_with_limit(
        Agent(id="a1", tenant="acme", name="Disabled", enabled=False), 1
    )
    with pytest.raises(PlanLimitError):
        await store.add_with_limit(
            Agent(id="a2", tenant="acme", name="Second", config={"archived": True}), 1
        )
    await store.add_with_limit(
        Agent(id="a3", tenant="acme", name="Unlimited", config={"archived": True}), -1
    )
    assert await store.count("acme") == 2


async def test_add_with_limit_serializes_concurrent_creates(tmp_path):
    """Two simultaneous add_with_limit calls for a tenant with limit 1 must produce exactly one agent.

    SQLite ignores SELECT FOR UPDATE, so the store also uses a per-tenant in-process lock to keep
    the count+insert atomic. This is the regression test for QIKO-1018.
    """
    sessionmaker = await _sm(tmp_path / "concurrent.db")
    async with sessionmaker() as session, session.begin():
        session.add(Tenant(id="acme", name="Acme"))
    store = SqlAgentStore(sessionmaker)

    creates = await asyncio.gather(
        store.add_with_limit(Agent(id="a1", tenant="acme", name="First"), 1),
        store.add_with_limit(Agent(id="a2", tenant="acme", name="Second"), 1),
        return_exceptions=True,
    )
    assert sum(isinstance(result, Agent) for result in creates) == 1
    assert sum(isinstance(result, PlanLimitError) for result in creates) == 1


@pytest.mark.skipif(not os.getenv("QIKO_TEST_POSTGRES_URL"), reason="temporary PostgreSQL required")
async def test_postgres_serializes_concurrent_limit_and_toggle():
    engine = create_async_engine(os.environ["QIKO_TEST_POSTGRES_URL"])
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session, session.begin():
        session.add(Tenant(id="acme", name="Acme"))
    store = SqlAgentStore(sessionmaker)

    creates = await asyncio.gather(
        store.add_with_limit(Agent(id="a1", tenant="acme", name="First"), 1),
        store.add_with_limit(Agent(id="a2", tenant="acme", name="Second"), 1),
        return_exceptions=True,
    )
    assert sum(isinstance(result, Agent) for result in creates) == 1
    assert sum(isinstance(result, PlanLimitError) for result in creates) == 1

    agent = (await store.list("acme"))[0]
    await asyncio.gather(
        store.set_enabled(
            "acme", agent.id, False, changed_by_email="admin.invalid", reason="first"
        ),
        store.set_enabled(
            "acme", agent.id, False, changed_by_email="admin.invalid", reason="second"
        ),
    )
    audit = await store.list_state_audit("acme")
    assert len(audit) == 1
    assert audit[0].previous_enabled is True and audit[0].enabled is False
    await engine.dispose()
