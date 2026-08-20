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
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Include agent_id in the id seed so the same doc ingested for two workers doesn't collide.
            pid = hashlib.sha1(f"{tenant}:{agent_id or ''}:{doc_id}:{i}".encode()).hexdigest()[:16]
            await self.store.add(Passage(id=pid, tenant=tenant, doc_id=doc_id, text=chunk,
                                         embedding=embedding, agent_id=agent_id))
        return len(chunks)

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
                       agent_id: str | None = None) -> list[Passage]:
        passages = await self.store.get(tenant, agent_id)  # tenant- (and optionally agent-) scoped
        if not passages:
            return []
        # Query embedding + cosine/bm25 scoring are network-/CPU-bound pure Python; run them off
        # the event loop so a large tenant corpus can't freeze the loop for the whole scoring pass.
        order = await asyncio.to_thread(self._rank, query, passages)
        return [passages[i] for i in order[:k]]

    def _rank(self, query: str, passages: list[Passage]) -> list[int]:
        qvec = self.embeddings.embed(query)
        dense = [retrieval.cosine(qvec, p.embedding) for p in passages]
        sparse = retrieval.bm25_scores(query, [p.text for p in passages])
        return retrieval.hybrid_order(dense, sparse)
