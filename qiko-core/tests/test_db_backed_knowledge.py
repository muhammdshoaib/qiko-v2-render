"""Proves the async KnowledgeService works end-to-end over the Postgres-backed SqlVectorStore
(exercised here on aiosqlite): ingest -> retrieve -> list -> delete, tenant-scoped."""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlVectorStore
from app.modules.knowledge.service import KnowledgeService

ISO = "IDG holds a current ISO 9001 certification valid through 2027."


async def _db_knowledge(path) -> KnowledgeService:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    return KnowledgeService(store=SqlVectorStore(sm))


async def test_db_backed_ingest_retrieve_delete(tmp_path):
    svc = await _db_knowledge(tmp_path / "k.db")
    assert await svc.ingest("acme", "iso", ISO) == 1
    await svc.ingest("beta", "secret", "Beta confidential pricing.")

    top = await svc.retrieve("acme", "ISO 9001 certification", k=1)
    assert top and "ISO 9001" in top[0].text
    # tenant isolation holds through the DB store
    assert await svc.retrieve("beta", "ISO 9001") == [] or all(
        "ISO 9001" not in p.text for p in await svc.retrieve("beta", "ISO 9001"))
    assert [d["doc_id"] for d in await svc.list_documents("acme")] == ["iso"]
    assert await svc.delete_document("acme", "iso") == 1
    assert await svc.list_documents("acme") == []


async def test_db_backed_tenant_wide_visible_to_worker(tmp_path):
    svc = await _db_knowledge(tmp_path / "k.db")
    await svc.ingest("acme", "shared-policy", "Shared policy covers ISO 9001.")

    top = await svc.retrieve("acme", "ISO 9001", k=1, agent_id="worker-1")
    assert top and "Shared policy" in top[0].text

