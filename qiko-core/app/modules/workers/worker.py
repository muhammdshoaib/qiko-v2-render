"""A Worker instance: knowledge + agentcore wired from a WorkerConfig. Every worker is created
this way, so shipping a new client worker is a config, not a new service."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.tenancy import reset_tenant, set_tenant
from app.modules.agentcore.generator import Generator
from app.modules.agentcore.models import AgentResult, Requirement
from app.modules.agentcore.runtime import AgentCore
from app.modules.ai import usage
from app.modules.ai.caps import CostCapExceeded
from app.modules.knowledge.models import Passage
from app.modules.knowledge.service import KnowledgeService
from app.modules.workers.config import WorkerConfig

WorkerRecheck = Callable[[], Awaitable[None]]


class StubProviderUnavailable(Exception):
    pass


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
    # Optional so every existing construction site keeps working and dev/tests run uncapped.
    cost_guard: object | None = None

    @property
    def name(self) -> str:
        return self.config.name

    async def ingest(self, doc_id: str, text: str) -> int:
        return await self.knowledge.ingest(self.config.tenant, doc_id, text, agent_id=self.config.agent_id)

    async def answer(self, requirement_id: str, requirement_text: str, *,
                     topic: str | None = None,
                     additional_context: list[str] | None = None,
                     recheck_worker: WorkerRecheck | None = None) -> AgentResult:
        # Bind the worker for AI cost attribution. Every model call in an answer (retrieval
        # embedding, generation, and any retry) happens below this frame, and AgentCore.run
        # deliberately takes no agent_id, so binding here avoids threading one through.
        agent_token = usage.set_agent(self.config.agent_id)
        tenant_token = set_tenant(self.config.tenant)
        try:
            # Checked once per answer, not per model call: an answer performs a retrieval embedding, a
            # generation and possibly retries, and a per-call check would put a database round trip in
            # front of each of them (QIK-522).
            if self.cost_guard is not None:
                decision = await self.cost_guard.check(self.config.tenant, self.config.agent_id)
                if not decision.allowed:
                    raise CostCapExceeded(decision)
            return await self._answer(requirement_id, requirement_text, topic=topic,
                                      additional_context=additional_context,
                                      recheck_worker=recheck_worker)
        finally:
            usage.reset_agent(agent_token)
            reset_tenant(tenant_token)

    async def _answer(self, requirement_id: str, requirement_text: str, *,
                      topic: str | None = None,
                      additional_context: list[str] | None = None,
                      recheck_worker: WorkerRecheck | None = None) -> AgentResult:
        if recheck_worker is not None:
            await recheck_worker()
        passages = await self.knowledge.retrieve(
            self.config.tenant, requirement_text, k=self.config.retrieval_k,
            agent_id=self.config.agent_id)
        if recheck_worker is not None:
            await recheck_worker()
        req = Requirement(id=requirement_id, text=requirement_text,
                          context=[p.text for p in passages] + list(additional_context or []),
                          topic=topic, sources=source_labels(passages))
        result = await self.agent.run(
            req, tenant=self.config.tenant, recheck_worker=recheck_worker)
        if result.stub and recheck_worker is not None:
            raise StubProviderUnavailable
        return result

    async def approve(self, requirement_id: str, approved_text: str, *,
                      topic: str | None = None, agent_id: str | None = None,
                      recheck_worker: WorkerRecheck | None = None) -> None:
        req = Requirement(id=requirement_id, text="", topic=topic)
        await self.agent.record_feedback(
            req, tenant=self.config.tenant, approved_text=approved_text,
            agent_id=agent_id, recheck_worker=recheck_worker)


def build_worker(config: WorkerConfig, *, provider=None, embeddings=None,
                 knowledge: KnowledgeService | None = None,
                 cost_guard: object | None = None) -> Worker:
    """Assemble a Worker from config over the shared engines. Provider/embeddings are injectable
    (defaults come from the ai gateway); the gate threshold and retrieval depth come from config.
    A pre-built knowledge service can be passed in so the worker shares the same vector store as
    the rest of the app (e.g. the intelligence chat endpoint)."""
    generator = Generator(provider=provider) if provider is not None else Generator()
    knowledge_service = knowledge if knowledge is not None else (
        KnowledgeService(embeddings=embeddings) if embeddings is not None else KnowledgeService())
    agent = AgentCore(generator=generator, threshold=config.gate_threshold)
    return Worker(config=config, knowledge=knowledge_service, agent=agent, cost_guard=cost_guard)
