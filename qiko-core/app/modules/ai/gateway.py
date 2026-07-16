"""Provider-agnostic AI gateway interface.

agentcore depends only on the LLMProvider protocol, so the concrete provider (AWS Bedrock/Claude
via inference profiles, with fallback) can be swapped in without touching the agent logic.
The concrete Bedrock provider is delivered in SCRUM-9; this module defines the contract and a
deterministic stub used for dev and tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings


@dataclass
class LLMResponse:
    text: str
    model: str = "stub"
    # True when the text came from the deterministic StubProvider (e.g. a Bedrock outage forced
    # the fallback). Such output is NOT a real grounded draft, so persistence paths can refuse it.
    stub: bool = False


class LLMProvider(Protocol):
    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> LLMResponse: ...


@dataclass
class StubProvider:
    """Deterministic provider for dev/tests. Echoes the supplied context so the grounding critic
    can be exercised end to end without a real model."""

    canned: str | None = None

    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> LLMResponse:
        if self.canned is not None:
            return LLMResponse(text=self.canned, stub=True)
        # Extract the CONTEXT block and reflect it back as the "answer" (fully grounded by design).
        context = ""
        if "CONTEXT:" in prompt:
            context = prompt.split("CONTEXT:", 1)[1].split("REQUIREMENT:", 1)[0].strip()
        return LLMResponse(text=context or "No supporting evidence was provided.", stub=True)


@dataclass
class FallbackProvider:
    """Try the primary provider; on any failure, fall back to a secondary provider (ADR-007).
    This is what keeps a Bedrock quota/outage, or a model missing in a Region, from breaking a run."""

    primary: LLMProvider
    fallback: LLMProvider

    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> LLMResponse:
        try:
            return self.primary.generate(prompt, system=system, temperature=temperature)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "primary AI provider failed; using fallback provider", exc_info=True)
            return self.fallback.generate(prompt, system=system, temperature=temperature)


def _build_one(name: str, *, read_timeout: int | None = None) -> LLMProvider:
    if name == "bedrock":
        from app.modules.ai.bedrock import BedrockProvider

        return BedrockProvider() if read_timeout is None else BedrockProvider(read_timeout=read_timeout)
    return StubProvider()


def get_provider(*, read_timeout: int | None = None) -> LLMProvider:
    """Build the provider from config: primary (default Bedrock) wrapped with a configured
    fallback. Model, Region and inference profile are config, not code (ADR-007/008).

    `read_timeout` overrides the default (tuned for the fast per-requirement answering hot path)
    for one-shot, whole-document calls (extraction/compliance/brief) that legitimately need
    longer -- see BedrockProvider.read_timeout."""
    s = get_settings()
    primary = _build_one(s.ai_provider, read_timeout=read_timeout)
    if s.ai_fallback_provider and s.ai_fallback_provider != s.ai_provider:
        return FallbackProvider(primary, _build_one(s.ai_fallback_provider, read_timeout=read_timeout))
    return primary
