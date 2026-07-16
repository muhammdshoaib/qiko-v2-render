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


@dataclass
class KnowledgeService:
    embeddings: EmbeddingsProvider = None  # type: ignore[assignment]
    store: VectorStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.embeddings is None:
            self.embeddings = get_embeddings()
        if self.store is None:
            self.store = InMemoryVectorStore()

    async def ingest(self, tenant: str, doc_id: str, text: str) -> int:
        chunks = chunk_text(text)
        # Embedding can be a blocking network call (e.g. Titan via boto3) or CPU-bound; run it off
        # the event loop so one ingest can't freeze every other request this process is handling.
        embeddings = await asyncio.to_thread(lambda: [self.embeddings.embed(c) for c in chunks])
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            pid = hashlib.sha1(f"{tenant}:{doc_id}:{i}".encode()).hexdigest()[:16]
            await self.store.add(Passage(id=pid, tenant=tenant, doc_id=doc_id, text=chunk,
                                         embedding=embedding))
        return len(chunks)

    async def ingest_file(self, tenant: str, doc_id: str, filename: str, data: bytes) -> int:
        """Parse an uploaded file to text, then chunk/embed/store it under doc_id."""
        return await self.ingest(tenant, doc_id, extract_text(filename, data))

    async def list_documents(self, tenant: str) -> list[dict]:
        """Distinct documents for a tenant with their chunk counts."""
        counts: dict[str, int] = {}
        for p in await self.store.get(tenant):
            counts[p.doc_id] = counts.get(p.doc_id, 0) + 1
        return [{"doc_id": d, "chunks": c} for d, c in sorted(counts.items())]

    async def delete_document(self, tenant: str, doc_id: str) -> int:
        """Remove a document's vectors (cascade). Returns chunks removed."""
        return await self.store.delete_doc(tenant, doc_id)

    async def retrieve(self, tenant: str, query: str, *, k: int = 5) -> list[Passage]:
        passages = await self.store.get(tenant)  # tenant-scoped by construction
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
