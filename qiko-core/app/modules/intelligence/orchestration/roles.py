"""Scout and Specialist for the Intelligence Worker.

Synthesizer, Critic and Magistrate are vertical-agnostic and live in
app.modules.agentcore.orchestration.roles; Scout and Specialist stay here because Scout is
genuinely Intelligence-specific (it reads Intelligence's signal/document stores). Each role is
stateless; all mutable state lives in the PipelineRun record managed by the runner.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.agentcore.orchestration.models import (
    EvidenceBundle,
    SpecialistOutput,
)
from app.modules.intelligence.documents import DocumentStore
from app.modules.intelligence.models import SignalStore
from app.modules.knowledge.service import KnowledgeService
from app.modules.workers.worker import Worker

DEFAULT_RETRIEVAL_K = 5
DEFAULT_SIGNAL_LIMIT = 50
SPECIALIST_CONCURRENCY = 5


class Scout:
    """Read-only evidence gathering. No LLM calls."""

    def __init__(
        self,
        knowledge: KnowledgeService,
        *,
        signal_store: SignalStore | None = None,
        document_store: DocumentStore | None = None,
        retrieval_k: int = DEFAULT_RETRIEVAL_K,
        signal_limit: int = DEFAULT_SIGNAL_LIMIT,
    ) -> None:
        self.knowledge = knowledge
        self.signal_store = signal_store
        self.document_store = document_store
        self.retrieval_k = retrieval_k
        self.signal_limit = signal_limit

    async def gather(
        self, tenant: str, agent_id: str, subject: str, *,
        context: list[str] | None = None,
    ) -> EvidenceBundle:
        text_chunks: list[str] = list(context or [])
        sources: list[str] = []

        passages = await self.knowledge.retrieve(
            tenant, subject, k=self.retrieval_k, agent_id=agent_id)
        text_chunks.extend([p.text for p in passages])
        sources.extend([p.doc_id for p in passages])

        signals: list = []
        if self.signal_store is not None:
            signals = await self.signal_store.list_recent(tenant, agent_id, limit=self.signal_limit)
            for s in signals:
                text_chunks.append(f"[{s.source}] {s.title}: {s.body}")
                sources.append(s.url or f"{s.source}:{s.external_id}")

        documents: list = []
        if self.document_store is not None:
            documents = await self.document_store.list(tenant, agent_id)
            for d in documents:
                text_chunks.append(f"[upload] {d.filename} ({d.status})")
                sources.append(d.doc_id)

        return EvidenceBundle(
            text_chunks=text_chunks,
            sources=_dedupe(sources),
        )


@dataclass
class Specialist:
    """One domain lens over an EvidenceBundle. Wraps the shared Worker/agentcore path."""

    worker: Worker

    async def work(self, bundle: EvidenceBundle, facet: str) -> SpecialistOutput:
        requirement_id = f"facet-{facet.replace(' ', '_').lower()[:32]}"
        text = f"Answer the following facet about the subject: {facet}"
        result = await self.worker.answer(
            requirement_id,
            text,
            topic=facet,
            additional_context=bundle.text_chunks,
        )
        return SpecialistOutput(
            facet=facet,
            answer=result.answer,
            confidence=result.confidence,
            gaps=result.gaps,
            citations=list(result.citations),
        )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
