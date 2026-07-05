"""A Worker instance: knowledge + agentcore wired from a WorkerConfig. Every worker is created
this way, so shipping a new client worker is a config, not a new service."""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.agentcore.generator import Generator
from app.modules.agentcore.models import AgentResult, Requirement
from app.modules.agentcore.runtime import AgentCore
from app.modules.knowledge.service import KnowledgeService
from app.modules.workers.config import WorkerConfig


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
                          context=[p.text for p in passages], topic=topic)
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
