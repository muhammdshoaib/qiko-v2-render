"""AgentCore: the reusable agentic engine every worker runs on.

Flow: generate -> independent critic (grounding) -> accept/escalate gate. Human-approved or edited
answers are recorded in the flywheel and override the AI draft for the same topic thereafter.
A worker is a configuration over this engine (provider, threshold, tools, knowledge), not a rewrite.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.modules.agentcore import critic as critic_mod
from app.modules.agentcore import gate as gate_mod
from app.modules.agentcore.flywheel import InMemoryVerifiedStore, VerifiedStore
from app.modules.agentcore.generator import Generator
from app.modules.agentcore.models import AgentResult, Requirement

WorkerRecheck = Callable[[], Awaitable[None]]


@dataclass
class AgentCore:
    generator: Generator = None  # type: ignore[assignment]
    verified: VerifiedStore = None  # type: ignore[assignment]
    threshold: float = gate_mod.DEFAULT_THRESHOLD

    def __post_init__(self) -> None:
        if self.generator is None:
            self.generator = Generator()
        if self.verified is None:
            self.verified = InMemoryVerifiedStore()

    async def run(self, req: Requirement, *, tenant: str,
                  recheck_worker: WorkerRecheck | None = None) -> AgentResult:
        topic = req.topic or req.id
        if recheck_worker is not None:
            await recheck_worker()
        verified = await self.verified.get(tenant, topic)
        if recheck_worker is not None:
            await recheck_worker()
        # generator.generate_structured() makes a blocking network call to the LLM provider. Run
        # it off the event loop thread -- otherwise one slow call freezes every other request this
        # process is handling (health checks included) for its entire duration, not just this one.
        gen = await asyncio.to_thread(self.generator.generate_structured, req, verified)
        if recheck_worker is not None:
            await recheck_worker()
        answer = gen.answer
        # The critic scores against the retrieved evidence plus any verified prior answers. This is
        # the GROUNDING score and stays independent of the writer's self-reported confidence.
        critique = critic_mod.grounding_score(answer, list(req.context) + verified)
        decision = gate_mod.decide(critique, threshold=self.threshold)
        # Confidence is the generator's own read of the evidence; when it did not self-report one
        # (plain-prose fallback) we derive it from grounding so the field is always populated.
        confidence = gen.confidence if gen.confidence is not None else critique.grounding
        # Citations are clean source labels (doc_id + short snippet) built by the worker; fall back
        # to the raw context only for callers that build a Requirement without sources.
        citations = list(req.sources) if req.sources else list(req.context)
        return AgentResult(requirement_id=req.id, answer=answer, critique=critique,
                           decision=decision, citations=citations,
                           confidence=round(confidence, 3), gaps=gen.gaps, stub=gen.stub)

    async def record_feedback(self, req: Requirement, *, tenant: str, approved_text: str,
                              agent_id: str | None = None,
                              recheck_worker: WorkerRecheck | None = None) -> None:
        """Human approval/edit becomes trusted ground truth for this tenant + topic."""
        topic = req.topic or req.id
        if agent_id is not None and recheck_worker is not None:
            await self.verified.add_for_enabled_agent(
                tenant, agent_id, topic, approved_text, recheck_worker)
            return
        await self.verified.add(tenant, topic, approved_text)
