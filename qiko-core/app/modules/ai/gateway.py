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
    # Token counts as reported by the provider. Bedrock returns these on every Converse call and
    # they used to be discarded. Defaulted so the stub and every test fake stay valid.
    input_tokens: int = 0
    output_tokens: int = 0
    # True when the provider stopped because it hit the output-token ceiling rather than because
    # the answer was finished. The text is then a PREFIX of the intended reply, which for a
    # structured (JSON) call means it cannot parse. Callers that require a complete document need
    # to be able to say "truncated" instead of blaming the model's JSON (QIKO-1081).
    truncated: bool = False


class LLMProvider(Protocol):
    # `prefill` seeds the start of the assistant turn (e.g. "{" to force a JSON object). Providers
    # that support it continue from the seed and return the seed prepended to the text; providers
    # that do not (the stub) ignore it. Optional and keyword-only so every existing caller is
    # unaffected.
    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2,
                 prefill: str | None = None) -> LLMResponse: ...


@dataclass
class StubProvider:
    """Deterministic provider for dev/tests. Echoes the supplied context so the grounding critic
    can be exercised end to end without a real model. `prefill` is accepted for interface parity
    but ignored: the stub is not a real model and never returns the JSON contract."""

    canned: str | None = None

    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2,
                 prefill: str | None = None) -> LLMResponse:
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

    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2,
                 prefill: str | None = None) -> LLMResponse:
        try:
            return self.primary.generate(prompt, system=system, temperature=temperature, prefill=prefill)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "primary AI provider failed; using fallback provider", exc_info=True)
            return self.fallback.generate(prompt, system=system, temperature=temperature, prefill=prefill)


def _build_one(name: str, *, read_timeout: int | None = None,
               max_tokens: int | None = None, model: str | None = None) -> LLMProvider:
    if name == "bedrock":
        from app.modules.ai.bedrock import BedrockProvider

        overrides = {k: v for k, v in
                     (("read_timeout", read_timeout), ("max_tokens", max_tokens),
                      ("model", model)) if v is not None}
        return BedrockProvider(**overrides)
    return StubProvider()


def get_provider(*, read_timeout: int | None = None,
                 max_tokens: int | None = None, model: str | None = None) -> LLMProvider:
    """Build the provider from config: primary (default Bedrock) wrapped with a configured
    fallback. Model, Region and inference profile are config, not code (ADR-007/008).

    `read_timeout` and `max_tokens` both override defaults tuned for the fast per-requirement
    answering hot path. One-shot, whole-document calls (extraction/compliance/brief) need more of
    each: longer to read tens of thousands of characters, and a bigger output ceiling because they
    must return a COMPLETE structured document rather than one short answer. Raising only the
    timeout leaves those calls silently truncated (QIKO-1081).

    `model` overrides the configured default model id (Settings.bedrock_model) for call sites that
    need a different Bedrock model tier than the app-wide default - e.g. the agentic pipeline's
    Specialist role, which makes many narrow, single-facet calls per run and uses a cheaper/faster
    tier than the pipeline's own Synthesizer/Critic roles (see agentcore.orchestration and
    app.tasks.jobs._build_idg_pipeline_deps)."""
    s = get_settings()
    primary = _build_one(s.ai_provider, read_timeout=read_timeout, max_tokens=max_tokens, model=model)
    if s.ai_fallback_provider and s.ai_fallback_provider != s.ai_provider:
        return FallbackProvider(primary, _build_one(s.ai_fallback_provider,
                                                    read_timeout=read_timeout,
                                                    max_tokens=max_tokens, model=model))
    return primary


# Output ceiling for a one-shot call that must return a COMPLETE structured document. A ten-section
# extraction already needs well over the 1024 default; twenty coarse sections with their
# sub-sections need several times that. Still bounded, so a runaway response cannot bill without
# limit.
DOCUMENT_MAX_TOKENS = 8192


def document_provider(*, read_timeout: int) -> LLMProvider:
    """Provider for a one-shot call over a whole document (extraction, brief, compliance, scoring).

    Exists so the two ceilings such a call needs, a longer read timeout and a bigger output
    budget, are raised TOGETHER. They were not: the timeout was made configurable and the token
    ceiling was left at the hot-path default, so extraction returned a truncated document and
    reported it as invalid JSON (QIKO-1081). Anything document-scale should call this rather than
    get_provider, so a new call site cannot repeat the omission."""
    return get_provider(read_timeout=read_timeout, max_tokens=DOCUMENT_MAX_TOKENS)
