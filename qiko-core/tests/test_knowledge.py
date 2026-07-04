from app.modules.knowledge.chunking import chunk_text
from app.modules.knowledge.models import Passage
from app.modules.knowledge.retrieval import bm25_scores, cosine, hybrid_order, rrf_fuse
from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.store import InMemoryVectorStore

ISO = "IDG holds a current ISO 9001 quality management certification valid through 2027."
HSE = "The health and safety policy covers site risk assessments and incident reporting."


# --- chunking ---
def test_chunk_empty():
    assert chunk_text("") == []


def test_chunk_single_and_multi():
    assert chunk_text("one paragraph") == ["one paragraph"]
    big = "\n\n".join(["para " + "x" * 300 for _ in range(5)])
    chunks = chunk_text(big, max_chars=400, overlap=20)
    assert len(chunks) > 1


# --- similarity primitives ---
def test_cosine():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([], [1.0]) == 0.0
    assert cosine([1.0], [1.0, 2.0]) == 0.0


def test_bm25_ranks_matching_doc_higher():
    docs = [ISO, HSE]
    scores = bm25_scores("ISO 9001 certification", docs)
    assert scores[0] > scores[1]
    assert bm25_scores("q", []) == []


def test_rrf_and_hybrid_order():
    fused = rrf_fuse([0, 1, 2], [0, 2, 1])
    assert max(fused, key=fused.get) == 0  # top of both lists wins
    # doc 1 is present in BOTH the dense and sparse rankings, so fusion rewards it over
    # docs that appear in only one ranking (the point of hybrid retrieval).
    order = hybrid_order([0.9, 0.1, 0.0], [0.0, 0.2, 0.8])
    assert order[0] == 1


# --- store isolation ---
async def test_store_tenant_isolation():
    s = InMemoryVectorStore()
    await s.add(Passage(id="1", tenant="acme", doc_id="d", text="x"))
    await s.add(Passage(id="2", tenant="beta", doc_id="d", text="y"))
    assert [p.id for p in await s.get("acme")] == ["1"]
    assert [p.id for p in await s.get("beta")] == ["2"]
    assert await s.get("nobody") == []


# --- service end to end ---
async def _service() -> KnowledgeService:
    svc = KnowledgeService()
    await svc.ingest("acme", "iso", ISO)
    await svc.ingest("acme", "hse", HSE)
    await svc.ingest("beta", "secret", "Beta confidential pricing structure.")
    return svc


async def test_ingest_returns_chunk_count():
    svc = KnowledgeService()
    assert await svc.ingest("acme", "iso", ISO) == 1


async def test_retrieve_is_relevant_and_tenant_scoped():
    svc = await _service()
    top = await svc.retrieve("acme", "ISO 9001 certification", k=1)
    assert len(top) == 1 and "ISO 9001" in top[0].text
    # tenant isolation: acme results never include beta's docs
    all_acme = await svc.retrieve("acme", "pricing structure", k=5)
    assert all("Beta confidential" not in p.text for p in all_acme)
    assert await svc.retrieve("nobody", "anything") == []
