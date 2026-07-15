"""Proves the RFP section->question tree works end-to-end over the Postgres-backed Sql stores
(exercised here on aiosqlite): CRUD -> lock roll-up -> overview, tenant-scoped."""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlPackQuestionStore, SqlPackSectionStore
from app.modules.rfp.tree import PackTreeService


async def _db_tree(path) -> PackTreeService:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
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
