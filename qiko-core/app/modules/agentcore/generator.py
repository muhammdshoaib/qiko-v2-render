"""Answer generator. Builds a grounded prompt (requirement + retrieved evidence + any verified
prior answers from the flywheel) and calls the LLM provider."""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.ai.gateway import LLMProvider, get_provider
from app.modules.agentcore.models import Requirement

SYSTEM = (
    "You are a bid-response writer. Answer the requirement using ONLY the supplied evidence. "
    "Do not invent facts, dates, names, or figures. If the evidence is insufficient, say so."
)


@dataclass
class Generator:
    provider: LLMProvider = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.provider is None:
            self.provider = get_provider()

    def build_prompt(self, req: Requirement, verified: list[str] | None = None) -> str:
        evidence = list(req.context) + list(verified or [])
        context_block = "\n".join(f"- {e}" for e in evidence) if evidence else "(none)"
        return f"CONTEXT:\n{context_block}\n\nREQUIREMENT:\n{req.text}\n"

    def generate(self, req: Requirement, verified: list[str] | None = None) -> str:
        prompt = self.build_prompt(req, verified)
        return self.provider.generate(prompt, system=SYSTEM).text.strip()
