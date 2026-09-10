"""Knowledge service: ingest (chunk -> embed -> store) and retrieve (hybrid, tenant-scoped)."""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

from app.modules.ai.embeddings import EmbeddingsProvider, get_embeddings
from app.modules.knowledge import retrieval
from app.modules.knowledge.chunking import chunk_text
from app.modules.knowledge.models import Passage
from app.modules.knowledge.parsing import extract_text
from app.modules.knowledge.store import InMemoryVectorStore, VectorStore


# Chunks either side of a hit to hand over with it. Chosen by measurement against the IDG KBR
# submission, on the question that exposed the defect ("details of all current projects"), counting
# how many of Form B8-2's thirteen project names reach the model:
#
#   radius 3 -> 10/12   radius 4 -> 12/12   radius 5 -> 12/12   radius 6 -> 12/12
#
# 4 is the smallest that returns the whole register. 5 and 6 buy nothing on this document and cost
# context. Before this change the same question put 3 of 12 in front of the model.
#
# The cost is real and worth knowing: at the default k this takes an answer's retrieved context
# from roughly 4 KB to roughly 29 KB, so about seven times the input tokens for the retrieval
# portion of each answer. That is the price of a complete table.
_WINDOW_RADIUS = 4
# Ceiling on one merged run, so a pathological document cannot swallow an answer's whole context.
_MAX_WIDENED_CHARS = 12_000


def _doc_name(sample: Passage | None, doc_id: str) -> str:
    if sample is None or not sample.text:
        return doc_id
    first = next((line.strip() for line in sample.text.splitlines() if line.strip()), "")
    return first[:120] or doc_id


@dataclass
class KnowledgeService:
    embeddings: EmbeddingsProvider = None  # type: ignore[assignment]
    store: VectorStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.embeddings is None:
            self.embeddings = get_embeddings()
        if self.store is None:
            self.store = InMemoryVectorStore()

    async def ingest(self, tenant: str, doc_id: str, text: str, *, agent_id: str | None = None) -> int:
        chunks = chunk_text(text)
        # Embedding can be a blocking network call (e.g. Titan via boto3) or CPU-bound; run it off
        # the event loop so one ingest can't freeze every other request this process is handling.
        embeddings = await asyncio.to_thread(lambda: [self.embeddings.embed(c) for c in chunks])
        passages = [
            Passage(
                # Include agent_id in the id seed so the same doc ingested for two workers doesn't collide.
                id=hashlib.sha1(f"{tenant}:{agent_id or ''}:{doc_id}:{i}".encode()).hexdigest()[:16],
                tenant=tenant, doc_id=doc_id, text=chunk, embedding=embedding, agent_id=agent_id,
                # Same `i` the id is seeded with, so ordinal and id can never disagree.
                ordinal=i,
            )
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        await self.store.add_all(passages)
        return len(passages)

    async def ingest_file(self, tenant: str, doc_id: str, filename: str, data: bytes,
                          *, agent_id: str | None = None) -> int:
        """Parse an uploaded file to text, then chunk/embed/store it under doc_id."""
        return await self.ingest(tenant, doc_id, extract_text(filename, data), agent_id=agent_id)

    async def list_documents(self, tenant: str, *, agent_id: str | None = None) -> list[dict]:
        """Distinct documents for a tenant (optionally scoped to one worker) with chunk counts.

        Per-worker listings show only that worker's own documents; the tenant-wide view (no
        agent_id) includes every document, disambiguated by agent_id when the passage is
        worker-scoped. Grouping by (doc_id, agent_id) prevents two workers from colliding on
        the same user-visible doc_id."""
        counts: dict[tuple[str, str | None], int] = {}
        sample: dict[tuple[str, str | None], Passage] = {}
        for p in await self.store.get(tenant, agent_id):
            if agent_id is not None and p.agent_id is None:
                continue
            key = (p.doc_id, p.agent_id)
            counts[key] = counts.get(key, 0) + 1
            sample.setdefault(key, p)
        result = []
        for (doc_id, doc_agent_id), c in sorted(counts.items()):
            item: dict = {"doc_id": doc_id, "name": _doc_name(sample.get((doc_id, doc_agent_id)), doc_id), "chunks": c}
            if doc_agent_id is not None:
                item["agent_id"] = doc_agent_id
            result.append(item)
        return result

    async def delete_document(self, tenant: str, doc_id: str, *, agent_id: str | None = None) -> int:
        """Remove a document's vectors (cascade), scoped to one worker when agent_id is given.
        Returns chunks removed."""
        return await self.store.delete_doc(tenant, doc_id, agent_id)

    async def retrieve(self, tenant: str, query: str, *, k: int = 5,
                       agent_id: str | None = None, doc_id: str | None = None) -> list[Passage]:
        """`doc_id` restricts retrieval to a single reference document (IDG-1000). There is no
        fallback: if that document holds nothing relevant, this returns nothing, and the caller's
        gate escalates rather than an answer being sourced from the wider knowledge base.

        The candidate set comes from the store's ANN path rather than a full corpus scan, and
        `doc_id` is pushed down into it. Scoping must happen in the store, not here: filtering an
        already-truncated top-k would silently return fewer passages than asked for, or none at
        all, whenever the reference document is not among the corpus-wide nearest neighbours."""
        qvec = await asyncio.to_thread(self.embeddings.embed, query)
        candidate_n = max(100, k * 10)
        passages = await self.store.search(tenant, qvec, k=candidate_n,
                                           agent_id=agent_id, doc_id=doc_id)
        if not passages:
            return []
        # Query embedding + cosine/bm25 scoring are network-/CPU-bound pure Python; run them off
        # the event loop so a large tenant corpus can't freeze the loop for the whole scoring pass.
        order = await asyncio.to_thread(self._rank, qvec, query, passages)
        return await self._widen(tenant, [passages[i] for i in order[:k]])

    async def _widen(self, tenant: str, hits: list[Passage]) -> list[Passage]:
        """Grow each hit into the contiguous run of text around it, MERGED into one passage.

        A tender's substance is in its tables, and an 800-character window cuts a thirteen-row
        project register into six chunks. Ranking returns some of them, so the model saw a
        fragment and answered from it: on a real IDG tender it named nine of thirteen projects and
        pulled three more from the neighbouring tables. Measured on that document, a window of
        +/-3 around the hit recovers the whole register in about 5.5 KB.

        The merge is the part that matters, and it is why this is not the neighbour-expansion that
        would have fought QIKO-1086. Returning the neighbours as SEPARATE passages would deliver
        the data and simultaneously guarantee the answer got flagged, because grounding requires a
        sentence to be supported by ONE passage and a summary of a thirteen-row table is supported
        by no single chunk of it. Merged, the passage the critic scores against contains the whole
        table, so the two changes agree.

        Windows that touch are merged into one, so overlapping hits inside the same table produce
        a single passage rather than repeated text. A passage with no ordinal (pre-migration-0050
        and unreconstructable) is returned untouched, which is exactly today's behaviour.
        """
        if not hits:
            return hits
        # Per document, collapse the hit ordinals into non-overlapping [lo, hi] spans.
        # Keyed by (doc_id, agent_id): a tenant-wide passage and a worker's passage can share a
        # doc_id, and their runs must not be merged into each other.
        spans: dict[tuple[str, str | None], list[list[int]]] = {}
        passthrough: list[Passage] = []
        for hit in hits:
            if hit.ordinal is None:
                passthrough.append(hit)
                continue
            lo, hi = hit.ordinal - _WINDOW_RADIUS, hit.ordinal + _WINDOW_RADIUS
            doc = spans.setdefault((hit.doc_id, hit.agent_id), [])
            for span in doc:
                if lo <= span[1] + 1 and span[0] <= hi + 1:   # touching or overlapping
                    span[0], span[1] = min(span[0], lo), max(span[1], hi)
                    break
            else:
                doc.append([lo, hi])

        out: list[Passage] = []
        for (doc_id, doc_agent), doc_spans in spans.items():
            for lo, hi in doc_spans:
                run = await self.store.neighbours(tenant, doc_id, max(0, lo), hi,
                                                  agent_id=doc_agent)
                if not run:
                    continue
                merged = "\n\n".join(p.text for p in run)
                # Bounded so one very long run cannot dominate an answer's context budget.
                if len(merged) > _MAX_WIDENED_CHARS:
                    merged = merged[:_MAX_WIDENED_CHARS]
                first = run[0]
                out.append(Passage(id=first.id, tenant=tenant, doc_id=doc_id, text=merged,
                                   agent_id=first.agent_id, ordinal=first.ordinal))
        return out + passthrough

    def _rank(self, qvec: list[float], query: str, passages: list[Passage]) -> list[int]:
        dense = [retrieval.cosine(qvec, p.embedding) for p in passages]
        sparse = retrieval.bm25_scores(query, [p.text for p in passages])
        return retrieval.hybrid_order(dense, sparse)
