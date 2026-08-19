from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlPipelineRunStore
from app.modules.intelligence.orchestration import (
    InMemoryPipelineRunStore,
    PipelineRun,
    PipelineRunStore,
)


def _run(**overrides) -> PipelineRun:
    base = dict(
        run_id="r1",
        tenant="t1",
        agent_id="w1",
        subject="research ACME",
        facets=["what they do", "open risks"],
        status={"scout": "pending"},
    )
    base.update(overrides)
    return PipelineRun(**base)


@pytest.fixture(params=["memory", "sql"])
async def store(request, tmp_path):
    if request.param == "memory":
        return InMemoryPipelineRunStore()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'pipeline_runs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlPipelineRunStore(async_sessionmaker(engine, expire_on_commit=False))


def test_protocol_is_satisfied_by_in_memory_store():
    assert isinstance(InMemoryPipelineRunStore(), PipelineRunStore)


def test_sql_store_satisfies_protocol():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store = SqlPipelineRunStore(async_sessionmaker(engine, expire_on_commit=False))
    assert isinstance(store, PipelineRunStore)


async def test_add_then_read_back(store):
    run = _run()
    await store.add(run)
    got = await store.get("t1", "w1", "r1")
    assert got is not None
    assert got.subject == "research ACME"
    assert got.facets == ["what they do", "open risks"]


async def test_list_orders_by_updated_at_newest_first(store):
    await store.add(_run(run_id="r1", subject="one"))
    await store.add(_run(run_id="r2", subject="two"))
    runs = await store.list("t1", "w1")
    assert [r.run_id for r in runs] == ["r2", "r1"]


async def test_update_persists_status_and_verdict(store):
    run = _run()
    await store.add(run)
    run.status["scout"] = "ready"
    run.verdict = "escalate"
    await store.update(run)
    got = await store.get("t1", "w1", "r1")
    assert got.status["scout"] == "ready"
    assert got.verdict == "escalate"


async def test_tenant_scoping_is_enforced(store):
    await store.add(_run(tenant="t1"))
    assert await store.get("t2", "w1", "r1") is None
    assert await store.list("t2", "w1") == []
