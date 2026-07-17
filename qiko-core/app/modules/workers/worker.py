"""A Worker instance: knowledge + agentcore wired from a WorkerConfig. Every worker is created
this way, so shipping a new client worker is a config, not a new service."""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.agentcore.generator import Generator
from app.modules.agentcore.models import AgentResult, Requirement
from app.modules.agentcore.runtime import AgentCore
from app.modules.knowledge.models import Passage
from app.modules.knowledge.service import KnowledgeService
from app.modules.workers.config import WorkerConfig


# Citations must be short SOURCE LABELS a UI can enumerate as "N Sources", never the raw passage
# body (which can be a whole table of contents).
def source_labels(passages: list[Passage]) -> list[str]:
    """Clean citation labels from retrieved passages: one per DISTINCT doc_id (first occurrence
    wins, original order kept), just the document name -- matches the idg cockpit, which lists the
    source documents as clean pills (not the raw passage body, not a doc+snippet blob)."""
    labels: list[str] = []
    seen: set[str] = set()
    for p in passages:
        doc_id = (p.doc_id or "").strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        labels.append(doc_id)
    return labels


@dataclass
class Worker:
    config: WorkerConfig
    knowledge: KnowledgeService
    agent: AgentCore

    @property
    def name(self) -> str:
        return self.config.name

    async def ingest(self, doc_id: str, text: str) -> int:
        return await self.knowledge.ingest(self.config.tenant, doc_id, text)

    async def answer(self, requirement_id: str, requirement_text: str, *, topic: str | None = None) -> AgentResult:
        passages = await self.knowledge.retrieve(self.config.tenant, requirement_text, k=self.config.retrieval_k)
        req = Requirement(id=requirement_id, text=requirement_text,
                          context=[p.text for p in passages], topic=topic,
                          sources=source_labels(passages))
        return await self.agent.run(req, tenant=self.config.tenant)

    async def approve(self, requirement_id: str, approved_text: str, *, topic: str | None = None) -> None:
        req = Requirement(id=requirement_id, text="", topic=topic)
        await self.agent.record_feedback(req, tenant=self.config.tenant, approved_text=approved_text)


def build_worker(config: WorkerConfig, *, provider=None, embeddings=None) -> Worker:
    """Assemble a Worker from config over the shared engines. Provider/embeddings are injectable
    (defaults come from the ai gateway); the gate threshold and retrieval depth come from config."""
    generator = Generator(provider=provider) if provider is not None else Generator()
    knowledge = KnowledgeService(embeddings=embeddings) if embeddings is not None else KnowledgeService()
    agent = AgentCore(generator=generator, threshold=config.gate_threshold)
    return Worker(config=config, knowledge=knowledge, agent=agent)
