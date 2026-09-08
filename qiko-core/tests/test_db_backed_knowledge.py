"""Proves the async KnowledgeService works end-to-end over the Postgres-backed SqlVectorStore
(exercised here on aiosqlite): ingest -> retrieve -> list -> delete, tenant-scoped."""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlVectorStore
from app.modules.knowledge.service import KnowledgeService

# Three tests here drop_all + create_all against the SAME test database as
# tests/test_agent_store.py and tests/test_db_backed_rfp_tree.py, so all three files share one
# xdist group: on separate workers they would drop each other's tables mid-test. Grouping the
# whole module rather than the three tests costs a little parallelism and removes the chance of
# the next Postgres test here being added without the mark.
pytestmark = pytest.mark.xdist_group("postgres_schema")


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


async def test_db_backed_agent_scoped_doc_id(tmp_path):
    svc = await _db_knowledge(tmp_path / "k.db")
    await svc.ingest("acme", "shared-name", ISO, agent_id="a1")
    await svc.ingest("acme", "shared-name", "Beta confidential pricing.", agent_id="a2")

    # Each worker sees only its own copy of the same user-visible doc_id.
    assert {d["doc_id"] for d in await svc.list_documents("acme", agent_id="a1")} == {"shared-name"}
    assert {d["doc_id"] for d in await svc.list_documents("acme", agent_id="a2")} == {"shared-name"}
    assert {d["agent_id"] for d in await svc.list_documents("acme")} == {"a1", "a2"}

    # Deleting one worker's copy leaves the other intact.
    assert await svc.delete_document("acme", "shared-name", agent_id="a1") >= 1
    assert {d["agent_id"] for d in await svc.list_documents("acme")} == {"a2"}

    # Tenant-wide deletion only removes shared (agent_id=None) documents.
    await svc.ingest("acme", "tenant-policy", "Tenant-wide policy.")
    await svc.ingest("acme", "tenant-policy", "Worker override.", agent_id="a2")
    assert await svc.delete_document("acme", "tenant-policy") == 1
    assert {d["doc_id"] for d in await svc.list_documents("acme", agent_id="a2")} == {"shared-name", "tenant-policy"}


# --- IDG-1001: single reference-document retrieval scoping, through the SQL store ---
async def test_db_backed_retrieve_scoped_to_a_single_document(tmp_path):
    svc = await _db_knowledge(tmp_path / "k.db")
    await svc.ingest("acme", "bid-2024", ISO)
    await svc.ingest("acme", "hse-policy", "Health and safety covers incident reporting.")

    hits = await svc.retrieve("acme", "ISO 9001 certification", k=5, doc_id="bid-2024")
    assert hits and {p.doc_id for p in hits} == {"bid-2024"}

    # No fallback: scoping to the document that does NOT answer the question returns nothing,
    # rather than the document that does.
    assert await svc.retrieve("acme", "incident reporting", k=5, doc_id="bid-2024") == []
    # ... and unscoped, that same question does reach hse-policy.
    assert {p.doc_id for p in await svc.retrieve("acme", "incident reporting", k=5)} == {"hse-policy"}

    assert await svc.retrieve("acme", "anything", k=5, doc_id="never-ingested") == []


async def test_db_backed_scoped_retrieve_never_crosses_tenants(tmp_path):
    """Both copies are relevant to the query on purpose: an empty result would satisfy a
    "no leakage" assertion for the wrong reason."""
    svc = await _db_knowledge(tmp_path / "k.db")
    await svc.ingest("acme", "shared-name", "Acme publishes its pricing structure openly.")
    await svc.ingest("beta", "shared-name", "Beta confidential pricing structure.")

    hits = await svc.retrieve("acme", "pricing structure", k=5, doc_id="shared-name")
    assert [p.text for p in hits] == ["Acme publishes its pricing structure openly."]


async def test_db_backed_scoped_retrieve_excludes_a_tenant_wide_doc_id_collision(tmp_path):
    svc = await _db_knowledge(tmp_path / "k.db")
    await svc.ingest("acme", "policy", "Worker copy: ISO 9001 certification is held.", agent_id="a1")
    await svc.ingest("acme", "policy", "Tenant-wide copy: ISO 9001 certification is held.")

    hits = await svc.retrieve("acme", "ISO 9001 certification", k=5, agent_id="a1", doc_id="policy")
    assert [p.text for p in hits] == ["Worker copy: ISO 9001 certification is held."]

    assert len(await svc.retrieve("acme", "ISO 9001 certification", k=5, agent_id="a1")) == 2


async def test_db_backed_scoped_retrieve_respects_the_agent_scope(tmp_path):
    svc = await _db_knowledge(tmp_path / "k.db")
    await svc.ingest("acme", "shared-name", ISO, agent_id="a1")
    await svc.ingest("acme", "shared-name", "Health and safety incident reporting.", agent_id="a2")

    a1 = await svc.retrieve("acme", "certification", k=5, agent_id="a1", doc_id="shared-name")
    assert a1 and all("Health and safety" not in p.text for p in a1)
async def test_search_falls_back_to_full_scan_on_sqlite(tmp_path):
    """SqlVectorStore.search() on SQLite (no vector type, no embedding_vec column) must behave
    exactly like today's get()-based ranking - this is the byte-for-byte SQLite compatibility
    this whole change is not allowed to break."""
    svc = await _db_knowledge(tmp_path / "k.db")
    await svc.ingest("acme", "iso", ISO)
    await svc.ingest("acme", "shared-name", "Beta confidential pricing.", agent_id="a2")
    via_retrieve = await svc.retrieve("acme", "ISO 9001 certification", k=1)
    assert via_retrieve and "ISO 9001" in via_retrieve[0].text

    # Directly exercise SqlVectorStore.search() (not just KnowledgeService.retrieve(), which
    # only ever calls store.get()) to prove its SQLite fallback branch actually delegates to
    # get() rather than merely being reachable-but-unverified code.
    store: SqlVectorStore = svc.store
    assert isinstance(store, SqlVectorStore)
    searched = await store.search("acme", [0.0] * 4, k=5)
    expected = await store.get("acme")
    assert [p.id for p in searched] == [p.id for p in expected]
    assert searched and all(p.tenant == "acme" for p in searched)

    # agent_id must also be forwarded through the fallback, matching get()'s tenant-wide +
    # worker-scoped visibility rules.
    searched_scoped = await store.search("acme", [0.0] * 4, k=5, agent_id="a2")
    expected_scoped = await store.get("acme", agent_id="a2")
    assert [p.id for p in searched_scoped] == [p.id for p in expected_scoped]
    assert {p.doc_id for p in searched_scoped} == {"iso", "shared-name"}


@pytest.mark.skipif(not os.getenv("QIKO_TEST_POSTGRES_URL"), reason="temporary PostgreSQL required")
async def test_postgres_search_uses_embedding_vec_and_returns_nearest_neighbors():
    from app.modules.knowledge.models import Passage

    engine = create_async_engine(os.environ["QIKO_TEST_POSTGRES_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # pgvector/pgvector:pg18 makes the `vector` TYPE available on the server but does not
        # itself run CREATE EXTENSION on any given database - that's a separate, explicit step
        # this create_all-based tier needs to do itself since it bypasses Alembic's 0004_pgvector
        # migration entirely.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # embedding_vec is deliberately not part of Base.metadata (raw SQL only, see Task 1's
        # migration) - apply the same DDL directly here rather than invoking Alembic's migration
        # runner against this shared, create_all-based Postgres tier (this codebase's existing
        # QIKO_TEST_POSTGRES_URL tests - test_agent_store.py, test_db_backed_rfp_tree.py - all use
        # drop_all/create_all for isolation, never real Alembic migrations; mixing Alembic's
        # version-tracked schema evolution into that same shared, per-test-dropped database would
        # make test order matter in a way nothing else in this tier does).
        await conn.execute(text("ALTER TABLE passages ADD COLUMN embedding_vec vector(4)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_passages_embedding_vec_hnsw "
            "ON passages USING hnsw (embedding_vec vector_cosine_ops)"))
    sm = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlVectorStore(sm)

    # 4-dim toy vectors (not the real 1024) so this test's assertions are hand-checkable: "near"
    # is obviously closer to the query than "far" by inspection, not by trusting the ranking math.
    near = Passage(id="p-near", tenant="acme", doc_id="d1", text="near passage",
                   embedding=[1.0, 0.0, 0.0, 0.0])
    far = Passage(id="p-far", tenant="acme", doc_id="d2", text="far passage",
                  embedding=[0.0, 0.0, 0.0, 1.0])
    await store.add_all([near, far])

    results = await store.search("acme", [0.9, 0.1, 0.0, 0.0], k=2)
    assert [p.id for p in results] == ["p-near", "p-far"]

    await engine.dispose()


@pytest.mark.skipif(not os.getenv("QIKO_TEST_POSTGRES_URL"), reason="temporary PostgreSQL required")
async def test_postgres_retrieve_end_to_end_with_more_rows_than_candidate_floor():
    from app.modules.knowledge.service import KnowledgeService

    engine = create_async_engine(os.environ["QIKO_TEST_POSTGRES_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE passages ADD COLUMN embedding_vec vector(1024)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_passages_embedding_vec_hnsw "
            "ON passages USING hnsw (embedding_vec vector_cosine_ops)"))
    sm = async_sessionmaker(engine, expire_on_commit=False)
    svc = KnowledgeService(store=SqlVectorStore(sm))

    # More rows than the default candidate floor (100 - see KnowledgeService.retrieve below),
    # the one behavior the SQLite tier structurally cannot exercise (SQLite never takes the ANN
    # branch, so it never narrows the corpus before ranking).
    for i in range(150):
        await svc.ingest("acme", f"doc-{i}", f"filler passage number {i} about nothing relevant")
    await svc.ingest("acme", "iso", ISO)

    top = await svc.retrieve("acme", "ISO 9001 certification", k=1)
    assert top and "ISO 9001" in top[0].text

    await engine.dispose()


@pytest.mark.skipif(not os.getenv("QIKO_TEST_POSTGRES_URL"), reason="temporary PostgreSQL required")
async def test_postgres_search_scopes_to_a_single_document():
    """IDG-1000's scoping, exercised on the ANN path rather than the fallback.

    Every other doc_id test in this file runs on SQLite, where SqlVectorStore.search() delegates
    straight to the full-scan get(). They would therefore all stay green with the Postgres branch
    of search() scoping wrongly, or not scoping at all, and the first sign of it would be a tender
    answer sourced from a document the UI promised was not used. This test is the one that fails
    if the doc_id clause is dropped from the SQL.
    """
    from app.modules.knowledge.models import Passage

    engine = create_async_engine(os.environ["QIKO_TEST_POSTGRES_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE passages ADD COLUMN embedding_vec vector(4)"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_passages_embedding_vec_hnsw "
            "ON passages USING hnsw (embedding_vec vector_cosine_ops)"))
    sm = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlVectorStore(sm)

    # The nearest neighbour by vector distance sits in the OTHER document on purpose: scoping has
    # to beat similarity, otherwise the filter is not actually being applied in the query.
    await store.add_all([
        Passage(id="p-other", tenant="acme", doc_id="hse-policy", text="nearest but out of scope",
                embedding=[1.0, 0.0, 0.0, 0.0]),
        Passage(id="p-scoped", tenant="acme", doc_id="bid-2024", text="in the reference document",
                embedding=[0.0, 1.0, 0.0, 0.0]),
    ])

    scoped = await store.search("acme", [0.9, 0.1, 0.0, 0.0], k=5, doc_id="bid-2024")
    assert [p.id for p in scoped] == ["p-scoped"]

    # Unscoped, the same query returns the genuinely nearest passage first, so the assertion above
    # is about the filter and not about the ranking being broken.
    unscoped = await store.search("acme", [0.9, 0.1, 0.0, 0.0], k=5)
    assert [p.id for p in unscoped][0] == "p-other"

    # Scoping to a document that holds nothing returns nothing rather than falling back.
    assert await store.search("acme", [0.9, 0.1, 0.0, 0.0], k=5, doc_id="missing") == []

    await engine.dispose()
