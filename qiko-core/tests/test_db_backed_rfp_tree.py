"""Proves the RFP section->question tree works end-to-end over the Postgres-backed Sql stores
(exercised here on aiosqlite): CRUD -> lock roll-up -> overview, tenant-scoped."""
import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import stores as stores_module
from app.db.base import Base
from app.db.models import Agent as AgentRow
from app.db.models import RfpPack as RfpPackRow
from app.db.models import Tenant
from app.db.stores import SqlPackQuestionStore, SqlPackSectionStore
from app.core.deps import WorkerUnavailable
from app.modules.rfp.tree import PackSection, PackTreeService

# These two modules each run Base.metadata.drop_all + create_all against the SAME test database,
# so under xdist they must never land on different workers at the same time: one would drop the
# other's tables mid-test. Same group name in both files keeps them on one worker, which also
# serialises them relative to each other.
pytestmark = pytest.mark.xdist_group("postgres_schema")



async def _db_tree(path) -> PackTreeService:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session, session.begin():
        session.add(Tenant(id="acme", name="Acme"))
        session.add(AgentRow(id="w1", tenant_id="acme", name="Worker", enabled=True))
        session.add(RfpPackRow(id="p1", tenant_id="acme", agent_id="w1", title="Tender"))
    return PackTreeService(sections=SqlPackSectionStore(sm), questions=SqlPackQuestionStore(sm))


async def test_db_backed_tree_lock_rollup(tmp_path):
    svc = await _db_tree(tmp_path / "tree.db")
    s = await svc.add_section("acme", "p1", code="A1", name="Intro")
    q1 = await svc.add_question("acme", s.id, text="Q1", word_limit=100)
    q2 = await svc.add_question("acme", s.id, text="Q2")

    await svc.apply_generation("acme", q1.id, ai_answer="draft", ai_sources=["doc:iso"],
                               confidence=0.8, decision="auto_accept", kb_gap=False)
    reloaded = await svc.get_question("acme", q1.id)
    assert reloaded.ai_answer == "draft" and reloaded.ai_sources == ["doc:iso"]

    await svc.lock_question("acme", q1.id)
    assert not await svc.all_sections_locked("acme", "p1")
    await svc.lock_question("acme", q2.id)
    assert (await svc.get_section("acme", s.id)).status == "locked"
    assert await svc.all_sections_locked("acme", "p1")

    ov = await svc.overview("acme", "p1")
    assert ov["sections_locked"] == 1 and ov["can_finalize"] is True


async def test_db_backed_tree_is_tenant_scoped(tmp_path):
    svc = await _db_tree(tmp_path / "tree2.db")
    s = await svc.add_section("acme", "p1", code="A1", name="Intro")
    await svc.add_question("acme", s.id, text="Q1")
    # another tenant sees nothing and cannot read the section
    assert await svc.sections.list("beta", "p1") == []
    assert await svc.sections.get("beta", s.id) is None
    assert await svc.questions.list("beta", "p1") == []


@pytest.mark.skipif(not os.getenv("QIKO_TEST_POSTGRES_URL"), reason="temporary PostgreSQL required")
async def test_postgres_disable_serializes_against_tree_persistence(monkeypatch):
    engine = create_async_engine(os.environ["QIKO_TEST_POSTGRES_URL"])
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session, session.begin():
        session.add(Tenant(id="acme", name="Acme"))
        session.add(AgentRow(id="w1", tenant_id="acme", name="Worker", enabled=True))
        session.add(RfpPackRow(id="p1", tenant_id="acme", agent_id="w1", title="Tender"))
    sections = SqlPackSectionStore(sm)
    locked = asyncio.Event()
    release = asyncio.Event()
    original = stores_module._lock_enabled_pack

    async def lock_then_pause(session, tenant, pack_id, **kwargs):
        pack = await original(session, tenant, pack_id, **kwargs)
        locked.set()
        await release.wait()
        return pack

    monkeypatch.setattr(stores_module, "_lock_enabled_pack", lock_then_pause)
    write = asyncio.create_task(sections.add(PackSection(
        id="s1", tenant="acme", pack_id="p1", code="A", name="Committed"
    )))
    await locked.wait()

    async def disable() -> None:
        async with sm() as session, session.begin():
            agent = await session.get(AgentRow, "w1", with_for_update=True)
            agent.enabled = False

    disabling = asyncio.create_task(disable())
    await asyncio.sleep(0.05)
    assert not disabling.done()
    release.set()
    await write
    await disabling
    with pytest.raises(WorkerUnavailable):
        await sections.add(PackSection(
            id="s2", tenant="acme", pack_id="p1", code="B", name="Blocked"
        ))
    assert [section.id for section in await sections.list("acme", "p1")] == ["s1"]
    await engine.dispose()
