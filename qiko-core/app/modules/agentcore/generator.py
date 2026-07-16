"""Answer generator. Builds a grounded prompt (requirement + retrieved evidence + any verified
prior answers from the flywheel) and calls the LLM provider."""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.ai.gateway import LLMProvider, LLMResponse, get_provider
from app.modules.agentcore.models import Requirement

SYSTEM = (
    "You are a bid-response writer. Answer the requirement using ONLY the supplied evidence. "
    "Do not invent facts, dates, names, or figures. If the evidence is insufficient, say so."
)

# Ingestion is supposed to chunk documents to ~800 chars (app.modules.knowledge.chunking), but a
# passage that slipped in unchunked (bulk-loaded, or from an older pipeline) can be tens of
# thousands of chars. One such passage among the retrieved evidence blows up the prompt to a size
# that made real Bedrock calls take minutes instead of seconds (observed live). Cap defensively
# here regardless of how the passage got that large -- retrieval should return a snippet, not a
# whole document.
_MAX_EVIDENCE_CHARS = 2000


@dataclass
class Generator:
    provider: LLMProvider = None  # type: ignore[assignment]
    # Per-worker override (see WorkerConfig.system_prompt / Agent.config["system_prompt"]) -- a
    # tender-answering worker and a pre-sales-writing worker are the same engine but must not
    # sound like the same person. Falls back to the generic bid-response-writer prompt.
    system_prompt: str | None = None

    def __post_init__(self) -> None:
        if self.provider is None:
            self.provider = get_provider()

    def build_prompt(self, req: Requirement, verified: list[str] | None = None) -> str:
        evidence = list(req.context) + list(verified or [])
        capped = [e[:_MAX_EVIDENCE_CHARS] + ("…" if len(e) > _MAX_EVIDENCE_CHARS else "") for e in evidence]
        context_block = "\n".join(f"- {e}" for e in capped) if capped else "(none)"
        return f"CONTEXT:\n{context_block}\n\nREQUIREMENT:\n{req.text}\n"

    def generate_response(self, req: Requirement, verified: list[str] | None = None) -> LLMResponse:
        """Full provider response (carries the `stub` flag) for callers that must know whether the
        text is a real grounded draft or a StubProvider fallback -- see AgentCore.run."""
        prompt = self.build_prompt(req, verified)
        return self.provider.generate(prompt, system=self.system_prompt or SYSTEM)

    def generate(self, req: Requirement, verified: list[str] | None = None) -> str:
        return self.generate_response(req, verified).text.strip()
