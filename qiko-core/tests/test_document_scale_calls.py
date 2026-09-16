"""QIKO-1081 / QIKO-1082: a one-shot call over a whole document must not be silently truncated,
and a truncation must not be reported as the model's fault.

Both defects were found by running a real IDG tender through the pipeline on preprod. Extraction
of a 2,174-character Expression of Interest returned exactly 1024 output tokens, cut mid-key, and
surfaced as "model did not return valid JSON" -- a ceiling we set, blamed on the model.
"""
import json

import pytest

from app.modules.agentcore.generator import _OUTPUT_CONTRACT, Generator
from app.modules.ai import gateway
from app.modules.ai.bedrock import BedrockProvider
from app.modules.ai.gateway import DOCUMENT_MAX_TOKENS, LLMResponse, document_provider, get_provider
from app.modules.rfp import extraction
from app.modules.rfp.extraction import ExtractionError


# --- the ceiling is configurable and defaults to the hot-path value -------------------------
def test_bedrock_defaults_to_the_hot_path_ceiling():
    """Unchanged for the per-requirement answering path, which is what 1024 was chosen for."""
    assert BedrockProvider(model="m", profile="", region="r").max_tokens == 1024


def test_document_provider_raises_both_ceilings_together(monkeypatch):
    """The point of the helper: a call site cannot raise the timeout and forget the token budget,
    which is exactly how the defect got in."""
    monkeypatch.setattr(gateway.get_settings(), "ai_provider", "bedrock")
    monkeypatch.setattr(gateway.get_settings(), "ai_fallback_provider", "")

    provider = document_provider(read_timeout=180)
    assert provider.read_timeout == 180
    assert provider.max_tokens == DOCUMENT_MAX_TOKENS
    assert DOCUMENT_MAX_TOKENS > 1024


def test_get_provider_without_overrides_is_unchanged(monkeypatch):
    monkeypatch.setattr(gateway.get_settings(), "ai_provider", "bedrock")
    monkeypatch.setattr(gateway.get_settings(), "ai_fallback_provider", "")

    provider = get_provider()
    assert provider.read_timeout == gateway.get_settings().ai_read_timeout_seconds
    assert provider.max_tokens == 1024


def test_the_ceiling_reaches_the_bedrock_call(monkeypatch):
    """Guards the wiring itself: the field must land in inferenceConfig, not just be stored."""
    sent = {}

    class _Client:
        def converse(self, **kwargs):
            sent.update(kwargs)
            return {"output": {"message": {"content": [{"text": "ok"}]}},
                    "stopReason": "end_turn", "usage": {"inputTokens": 1, "outputTokens": 1}}

    provider = BedrockProvider(model="m", profile="", region="r", max_tokens=4242)
    monkeypatch.setattr(provider, "_client", lambda: _Client())
    monkeypatch.setattr("app.modules.ai.usage.record", lambda *a, **k: None)

    provider.generate("hello")
    assert sent["inferenceConfig"]["maxTokens"] == 4242


# --- truncation is detected and reported honestly --------------------------------------------
@pytest.mark.parametrize(("stop_reason", "expected"), [("max_tokens", True), ("end_turn", False)])
def test_truncation_is_reported_on_the_response(monkeypatch, stop_reason, expected):
    class _Client:
        def converse(self, **_kwargs):
            return {"output": {"message": {"content": [{"text": "partial"}]}},
                    "stopReason": stop_reason, "usage": {"inputTokens": 1, "outputTokens": 1024}}

    provider = BedrockProvider(model="m", profile="", region="r")
    monkeypatch.setattr(provider, "_client", lambda: _Client())
    monkeypatch.setattr("app.modules.ai.usage.record", lambda *a, **k: None)

    assert provider.generate("hello").truncated is expected


def test_a_missing_stop_reason_is_not_treated_as_truncation(monkeypatch):
    """Read defensively, like the usage block: a shape surprise must not turn a good answer into
    an error."""
    class _Client:
        def converse(self, **_kwargs):
            return {"output": {"message": {"content": [{"text": "complete"}]}}}

    provider = BedrockProvider(model="m", profile="", region="r")
    monkeypatch.setattr(provider, "_client", lambda: _Client())
    monkeypatch.setattr("app.modules.ai.usage.record", lambda *a, **k: None)

    assert provider.generate("hello").truncated is False


def test_truncated_extraction_names_the_ceiling_not_the_model():
    """The message a person reads at 2am. "invalid JSON" sent people hunting a model or prompt
    problem; the cause was a constant in our own code."""
    cut = json.dumps([{"id": "1", "title": "A", "classification": "KB",
                       "requirement": "x", "subsections": []}])[:-12]

    class _Truncating:
        def generate(self, _prompt, **_kwargs):
            return LLMResponse(text=cut, truncated=True)

    with pytest.raises(ExtractionError) as caught:
        extraction.extract_requirements("some tender text", _Truncating())
    message = str(caught.value)
    assert "output-token ceiling" in message
    assert "cut off" in message
    assert "did not return valid JSON" not in message


def test_genuinely_malformed_json_still_reports_as_malformed():
    """The truncation branch must not swallow the ordinary case."""
    class _Garbage:
        def generate(self, _prompt, **_kwargs):
            return LLMResponse(text="[{not json at all", truncated=False)

    with pytest.raises(ExtractionError) as caught:
        extraction.extract_requirements("some tender text", _Garbage())
    assert "did not return valid JSON" in str(caught.value)


# --- QIKO-1082: refusing is an explicit, permitted option -------------------------------------
def test_the_contract_permits_refusing_when_the_evidence_is_off_topic():
    """Retrieval matches a question's words, not its meaning, so the model is routinely handed
    passages that do not answer what was asked. Without an explicit instruction it summarises them,
    and the grounding critic cannot object because the summary IS the evidence."""
    assert "addresses THE QUESTION ASKED" in _OUTPUT_CONTRACT
    assert "does not cover this question" in _OUTPUT_CONTRACT


def test_every_worker_gets_the_relevance_rule_including_persona_workers():
    """It lives in the output contract, which is applied for every worker. A synthesized persona
    (QIK-315) replaces the identity, and the IDG pre-sales worker has one, so a rule placed in the
    identity would be lost for exactly the workers that need it."""
    from app.modules.ai.gateway import StubProvider

    default = Generator(provider=StubProvider()).system
    persona = Generator(provider=StubProvider(), system_prompt="You are IDG's bid writer.").system
    for prompt in (default, persona):
        assert "addresses THE QUESTION ASKED" in prompt
    assert "You are IDG's bid writer." in persona
