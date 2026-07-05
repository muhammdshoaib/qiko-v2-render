"""AgentCore: the reusable agentic engine every worker runs on.

Flow: generate -> independent critic (grounding) -> accept/escalate gate. Human-approved or edited
answers are recorded in the flywheel and override the AI draft for the same topic thereafter.
A worker is a configuration over this engine (provider, threshold, tools, knowledge), not a rewrite.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.agentcore import critic as critic_mod
from app.modules.agentcore import gate as gate_mod
from app.modules.agentcore.flywheel import InMemoryVerifiedStore, VerifiedStore
from app.modules.agentcore.generator import Generator
from app.modules.agentcore.models import AgentResult, Requirement


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

    async def run(self, req: Requirement, *, tenant: str) -> AgentResult:
        topic = req.topic or req.id
        verified = await self.verified.get(tenant, topic)
        answer = self.generator.generate(req, verified=verified)
        # The critic scores against the retrieved evidence plus any verified prior answers.
        critique = critic_mod.grounding_score(answer, list(req.context) + verified)
        decision = gate_mod.decide(critique, threshold=self.threshold)
        return AgentResult(requirement_id=req.id, answer=answer, critique=critique,
                           decision=decision, citations=list(req.context))

    async def record_feedback(self, req: Requirement, *, tenant: str, approved_text: str) -> None:
        """Human approval/edit becomes trusted ground truth for this tenant + topic."""
        topic = req.topic or req.id
        await self.verified.add(tenant, topic, approved_text)
