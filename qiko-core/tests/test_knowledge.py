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


async def test_embed_and_scoring_run_off_the_event_loop():
    """ingest (embed) and retrieve (embed + cosine/bm25 scoring) must run in a worker thread, not
    on the async event loop -- a blocking Titan boto3 embed would otherwise freeze the whole loop.
    A worker thread has no running event loop, so asyncio.get_running_loop() raising there proves
    the work was offloaded."""
    import asyncio

    class _LoopProbeEmbeddings:
        dim = 8

        def embed(self, text: str) -> list[float]:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return [1.0] + [0.0] * 7  # off the loop (in a thread) -- as required
            raise AssertionError("embed ran on the event loop thread")

    svc = KnowledgeService(embeddings=_LoopProbeEmbeddings())
    assert await svc.ingest("acme", "d", "some text to embed") == 1
    assert len(await svc.retrieve("acme", "query")) == 1


async def test_retrieve_is_relevant_and_tenant_scoped():
    svc = await _service()
    top = await svc.retrieve("acme", "ISO 9001 certification", k=1)
    assert len(top) == 1 and "ISO 9001" in top[0].text
    # tenant isolation: acme results never include beta's docs
    all_acme = await svc.retrieve("acme", "pricing structure", k=5)
    assert all("Beta confidential" not in p.text for p in all_acme)
    assert await svc.retrieve("nobody", "anything") == []


# --- QIK-315: per-worker (agent_id) knowledge scoping ---
async def test_ingest_and_retrieve_are_agent_scoped():
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "idg-doc", ISO, agent_id="idg")
    await svc.ingest("acme", "hse-doc", HSE, agent_id="support")

    idg_docs = {d["doc_id"] for d in await svc.list_documents("acme", agent_id="idg")}
    support_docs = {d["doc_id"] for d in await svc.list_documents("acme", agent_id="support")}
    assert idg_docs == {"idg-doc"} and support_docs == {"hse-doc"}  # no cross-worker bleed

    # retrieval for the support worker never returns the IDG passage (QIK-315 core fix)
    idg_hits = [p.doc_id for p in await svc.retrieve("acme", "ISO certification", agent_id="idg")]
    support_hits = [p.doc_id for p in await svc.retrieve("acme", "ISO certification", agent_id="support")]
    assert "idg-doc" in idg_hits and "idg-doc" not in support_hits

    # tenant-wide (no agent_id) still sees everything (legacy/internal callers)
    assert len(await svc.list_documents("acme")) == 2


async def test_list_documents_includes_readable_name():
    svc = KnowledgeService(store=InMemoryVectorStore())
    # Source-style documents put a human-readable title on the first line.
    await svc.ingest("acme", "site", "Company homepage\nhttps://example.com\nDetails here.")
    docs = await svc.list_documents("acme")
    assert docs == [{"doc_id": "site", "name": "Company homepage", "chunks": 1}]


async def test_delete_is_agent_scoped():
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "shared-name", ISO, agent_id="a1")
    await svc.ingest("acme", "shared-name", HSE, agent_id="a2")  # same doc_id, different worker
    removed = await svc.delete_document("acme", "shared-name", agent_id="a1")
    assert removed >= 1
    assert {d["doc_id"] for d in await svc.list_documents("acme", agent_id="a2")} == {"shared-name"}
    assert await svc.list_documents("acme", agent_id="a1") == []


async def test_list_documents_scopes_same_doc_id_by_agent():
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "shared-name", ISO, agent_id="a1")
    await svc.ingest("acme", "shared-name", HSE, agent_id="a2")

    # The tenant-wide view must not merge the two workers into a single doc entry.
    all_docs = await svc.list_documents("acme")
    assert len(all_docs) == 2
    assert all(d["doc_id"] == "shared-name" for d in all_docs)
    assert {d["agent_id"] for d in all_docs} == {"a1", "a2"}

    # Per-worker listings still return exactly one entry for the caller's copy.
    assert [d["agent_id"] for d in await svc.list_documents("acme", agent_id="a1")] == ["a1"]
    assert [d["agent_id"] for d in await svc.list_documents("acme", agent_id="a2")] == ["a2"]


async def test_unscoped_retrieve_returns_all_worker_corpora():
    """A retrieve call with no agent_id is the intentional tenant-wide view: it sees every
    worker's corpus (plus shared tenant-wide passages) so admin/internal callers can search
    the whole tenant."""
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "w1-doc", "Worker one knows alpha.", agent_id="w1")
    await svc.ingest("acme", "w2-doc", "Worker two knows beta.", agent_id="w2")
    await svc.ingest("acme", "shared-doc", "Shared knowledge covers gamma.")

    hits = {p.doc_id for p in await svc.retrieve("acme", "alpha beta gamma", k=10)}
    assert hits == {"w1-doc", "w2-doc", "shared-doc"}


async def test_tenant_wide_knowledge_is_visible_to_all_workers():
    """Legacy/internal documents ingested without an agent_id are shared across the tenant and
    must be retrievable by every worker; per-worker listings still hide them from the library view."""
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "company-policy", "Company policy covers ISO 9001 compliance.")

    hits = [p.doc_id for p in await svc.retrieve("acme", "ISO 9001 compliance", agent_id="worker-1")]
    assert "company-policy" in hits

    hits = [p.doc_id for p in await svc.retrieve("acme", "ISO 9001 compliance", agent_id="worker-2")]
    assert "company-policy" in hits

    assert await svc.list_documents("acme", agent_id="worker-1") == []
    assert {d["doc_id"] for d in await svc.list_documents("acme")} == {"company-policy"}


# --- IDG-1001: single reference-document retrieval scoping ---
async def test_store_get_filters_by_doc_id():
    s = InMemoryVectorStore()
    await s.add(Passage(id="1", tenant="acme", doc_id="bid-2024", text="x"))
    await s.add(Passage(id="2", tenant="acme", doc_id="policies", text="y"))
    assert [p.id for p in await s.get("acme", None, "bid-2024")] == ["1"]
    assert await s.get("acme", None, "no-such-doc") == []
    # Unscoped stays exactly as before.
    assert {p.id for p in await s.get("acme")} == {"1", "2"}


async def test_retrieve_scoped_to_a_single_document():
    svc = await _service()
    hits = await svc.retrieve("acme", "ISO 9001 certification", k=5, doc_id="iso")
    assert hits and {p.doc_id for p in hits} == {"iso"}


async def test_scoped_retrieve_has_no_fallback_to_the_wider_knowledge_base():
    """The acceptance criterion that matters most. When the reference document is a poor match
    for the question, retrieval must stay inside it rather than quietly returning the document
    that answers the question better. A silent fallback here would produce an answer that reads
    as correct while being sourced from outside the bid the customer scoped to.

    Note the scoped result here is EMPTY rather than weak: retrieval._rank keeps only positive
    scores, so a reference document with no relevance to the question contributes nothing. That
    is the intended "insufficient detail in the reference document" path -- no evidence reaches
    the generator, so the gate escalates instead of an answer being invented."""
    svc = await _service()
    # "hse" is the document that actually answers this; scoped to "iso", nothing may come back.
    hits = await svc.retrieve("acme", "health and safety incident reporting", k=5, doc_id="iso")
    assert hits == []

    # Unscoped, the very same question does reach "hse" -- which is what makes the assertion
    # above meaningful rather than an accident of the corpus.
    unscoped = await svc.retrieve("acme", "health and safety incident reporting", k=5)
    assert {p.doc_id for p in unscoped} == {"hse"}


async def test_scoped_retrieve_never_crosses_tenants():
    """A doc_id is only unique within a tenant, so scoping must never become a way to name
    another tenant's document. Both copies are made relevant to the query on purpose: an empty
    result would pass this assertion for the wrong reason, so the caller's copy must actually
    come back while the other tenant's stays invisible."""
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "shared-name", "Acme publishes its pricing structure openly.")
    await svc.ingest("beta", "shared-name", "Beta confidential pricing structure.")

    hits = await svc.retrieve("acme", "pricing structure", k=5, doc_id="shared-name")
    assert [p.text for p in hits] == ["Acme publishes its pricing structure openly."]
    assert await svc.retrieve("nobody", "anything", doc_id="shared-name") == []


async def test_scoped_retrieve_still_respects_the_agent_scope():
    """doc_id narrows within the worker's corpus; it does not widen it. Two workers holding the
    same doc_id must not see each other's copy."""
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "shared-name", ISO, agent_id="a1")
    await svc.ingest("acme", "shared-name", HSE, agent_id="a2")

    a1 = await svc.retrieve("acme", "certification", k=5, agent_id="a1", doc_id="shared-name")
    assert a1 and all("health and safety" not in p.text for p in a1)


async def test_scoped_retrieve_excludes_a_tenant_wide_document_sharing_the_doc_id():
    """A scoped job must draw on ONE document, and the picker only ever offers the worker's own
    (list_documents hides tenant-wide ones from a per-worker listing). Unscoped worker retrieval
    deliberately also sees tenant-wide passages, so without an explicit carve-out a scope would
    quietly pull in a tenant-wide document that happens to share the doc_id -- while the cockpit
    tells the reviewer nothing else was used."""
    svc = KnowledgeService(store=InMemoryVectorStore())
    await svc.ingest("acme", "policy", "Worker copy: ISO 9001 certification is held.", agent_id="a1")
    await svc.ingest("acme", "policy", "Tenant-wide copy: ISO 9001 certification is held.")

    hits = await svc.retrieve("acme", "ISO 9001 certification", k=5, agent_id="a1", doc_id="policy")
    assert [p.text for p in hits] == ["Worker copy: ISO 9001 certification is held."]

    # Unscoped worker retrieval is unchanged: it still sees the shared tenant-wide passage.
    unscoped = await svc.retrieve("acme", "ISO 9001 certification", k=5, agent_id="a1")
    assert len(unscoped) == 2


async def test_scoped_retrieve_to_an_empty_document_returns_nothing():
    """No passages in scope means no evidence, which is what lets the gate escalate rather than
    the generator inventing an answer."""
    svc = await _service()
    assert await svc.retrieve("acme", "anything at all", k=5, doc_id="never-ingested") == []


async def test_unscoped_retrieve_is_unchanged_by_the_scoping_feature():
    """Regression guard: the default path must behave exactly as it did before doc_id existed.
    Each question reaches the document that answers it, and only that one, because zero-relevance
    passages are dropped by retrieval._rank."""
    svc = await _service()
    assert {p.doc_id for p in await svc.retrieve("acme", "ISO 9001 certification", k=5)} == {"iso"}
    assert {p.doc_id for p in await svc.retrieve("acme", "health and safety incident reporting", k=5)} == {"hse"}


