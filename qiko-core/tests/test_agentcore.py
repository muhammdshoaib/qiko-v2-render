import pytest
from pydantic import BaseModel

from app.modules.agentcore import critic, gate
from app.modules.agentcore.flywheel import InMemoryVerifiedStore
from app.modules.agentcore.generator import Generator, parse_structured
from app.modules.agentcore.models import Critique, Decision, Requirement
from app.modules.agentcore.runtime import AgentCore
from app.modules.agentcore.tools import ToolError, ToolRegistry
from app.modules.ai.gateway import LLMResponse, StubProvider


class _CannedProvider:
    """Returns a fixed text regardless of prompt (not flagged as a stub), so a structured JSON
    contract can be exercised without a real model."""

    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2):
        return LLMResponse(text=self.text, stub=False)

ISO_EVIDENCE = ["IDG holds a current ISO 9001 quality management certification valid through 2027."]


# --- gateway / generator ---
def test_stub_provider_echoes_context():
    gen = Generator(provider=StubProvider())
    req = Requirement(id="B1", text="Describe your QMS.", context=ISO_EVIDENCE)
    answer = gen.generate(req)
    assert "ISO 9001" in answer


def test_stub_provider_canned():
    assert StubProvider(canned="hello").generate("x").text == "hello"


def test_build_prompt_includes_verified():
    gen = Generator(provider=StubProvider())
    req = Requirement(id="B1", text="Q", context=["a"])
    prompt = gen.build_prompt(req, verified=["b"])
    assert "- a" in prompt and "- b" in prompt and "REQUIREMENT:" in prompt


def test_build_prompt_caps_oversized_evidence():
    # A passage that skipped chunking (bulk-loaded, older pipeline, etc.) can be tens of
    # thousands of chars; one of those in the retrieved evidence blew up a real prompt enough to
    # make Bedrock calls take minutes. build_prompt must never pass an unbounded passage through.
    gen = Generator(provider=StubProvider())
    huge = "x" * 50_000
    req = Requirement(id="B1", text="Q", context=[huge])
    prompt = gen.build_prompt(req)
    assert len(prompt) < 10_000


# --- structured generator output (answer + self-reported confidence + gaps) ---
def test_parse_structured_plain_json():
    parsed = parse_structured('{"answer": "We hold ISO 9001.", "confidence": 0.7, "gaps": "no SLA"}')
    assert parsed == ("We hold ISO 9001.", 0.7, "no SLA")


def test_parse_structured_tolerates_json_fence_and_clamps():
    parsed = parse_structured('```json\n{"answer": "A", "confidence": 1.4, "gaps": ""}\n```')
    assert parsed == ("A", 1.0, "")  # confidence clamped into 0..1


def test_parse_structured_returns_none_for_plain_prose():
    assert parse_structured("Just prose, no JSON here.") is None
    assert parse_structured("") is None


def test_generator_structured_reports_confidence_and_gaps_distinct_from_grounding():
    """The generator's self-reported confidence and gaps come from the model, and are NOT the
    same number as the independent grounding critic computes over the prose."""
    payload = '{"answer": "IDG holds ISO 9001 certification.", "confidence": 0.55, "gaps": "no audit dates"}'
    gen = Generator(provider=_CannedProvider(payload))
    req = Requirement(id="B1", text="Describe your QMS.", context=ISO_EVIDENCE)
    out = gen.generate_structured(req)
    assert out.answer == "IDG holds ISO 9001 certification."
    assert out.confidence == 0.55 and out.gaps == "no audit dates"
    # grounding, scored independently by the critic over the same answer/evidence, differs
    grounding = critic.grounding_score(out.answer, ISO_EVIDENCE).grounding
    assert grounding != out.confidence


def test_generator_structured_falls_back_to_prose_when_not_json():
    gen = Generator(provider=_CannedProvider("plain prose answer, no json"))
    out = gen.generate_structured(Requirement(id="B1", text="Q", context=ISO_EVIDENCE))
    assert out.answer == "plain prose answer, no json"
    assert out.confidence is None and out.gaps == ""  # caller derives confidence from grounding


async def test_runtime_confidence_distinct_from_grounding():
    """End to end: a self-reported confidence flows to AgentResult.confidence, while
    critique.grounding stays the independent score, so the two are genuinely distinct."""
    payload = ('{"answer": "IDG holds a current ISO 9001 quality management certification '
               'valid through 2027.", "confidence": 0.5, "gaps": "pricing not covered"}')
    core = AgentCore(generator=Generator(provider=_CannedProvider(payload)))
    req = Requirement(id="B1", text="Describe your QMS.", context=ISO_EVIDENCE, topic="qms")
    result = await core.run(req, tenant="acme")
    assert result.confidence == 0.5 and result.gaps == "pricing not covered"
    assert result.critique.grounding == 1.0  # fully grounded prose
    assert result.confidence != result.critique.grounding


async def test_runtime_confidence_falls_back_to_grounding_without_selfreport():
    """When the model returns plain prose (no confidence), confidence is derived from grounding."""
    core = AgentCore(generator=Generator(provider=StubProvider()))
    req = Requirement(id="B1", text="Describe your QMS.", context=ISO_EVIDENCE, topic="qms")
    result = await core.run(req, tenant="acme")
    assert result.confidence == round(result.critique.grounding, 3)


# --- critic ---
def test_grounding_full():
    c = critic.grounding_score("IDG holds ISO 9001 certification valid through 2027.", ISO_EVIDENCE)
    assert c.grounding == 1.0 and c.issues == []


def test_grounding_low_flags_issues():
    c = critic.grounding_score("Our spaceship fleet orbits Jupiter every fortnight.", ISO_EVIDENCE)
    assert c.grounding < 0.5 and c.issues


def test_grounding_empty():
    assert critic.grounding_score("", ISO_EVIDENCE).grounding == 0.0


# --- gate ---
def test_gate_thresholds():
    assert gate.decide(Critique(grounding=0.9)) is Decision.auto_accept
    assert gate.decide(Critique(grounding=0.5)) is Decision.human_review
    assert gate.decide(Critique(grounding=1.0), hard_fail=True) is Decision.human_review


# --- flywheel ---
async def test_flywheel_add_get_dedupe_scoping():
    s = InMemoryVerifiedStore()
    await s.add("acme", "qms", "answer one")
    await s.add("acme", "qms", "answer one")  # dedupe
    await s.add("acme", "qms", "  ")          # empty ignored
    assert await s.get("acme", "qms") == ["answer one"]
    assert await s.get("other", "qms") == []  # tenant-scoped


# --- tools ---
async def test_tool_registry_invoke_and_validation():
    reg = ToolRegistry()

    class Args(BaseModel):
        n: int

    @reg.register("double", Args)
    def _double(a: Args) -> int:
        return a.n * 2

    assert reg.names() == ["double"]
    assert await reg.invoke("double", {"n": 21}) == 42
    with pytest.raises(ToolError):
        await reg.invoke("double", {"n": "not-an-int"})
    with pytest.raises(ToolError):
        await reg.invoke("missing", {})


async def test_tool_registry_wraps_handler_failures_as_tool_error():
    """A real gateway call (Stripe/Calendly/Slack/...) blowing up must not leak a raw exception."""
    reg = ToolRegistry()

    class Args(BaseModel):
        pass

    @reg.register("flaky", Args)
    def _flaky(_a: Args) -> None:
        raise RuntimeError("upstream API said no")

    with pytest.raises(ToolError, match="flaky failed"):
        await reg.invoke("flaky", {})


# --- runtime end-to-end ---
async def test_runtime_auto_accepts_grounded_answer():
    core = AgentCore(generator=Generator(provider=StubProvider()))
    req = Requirement(id="B1", text="Describe your QMS.", context=ISO_EVIDENCE, topic="qms")
    result = await core.run(req, tenant="acme")
    assert result.decision is Decision.auto_accept
    assert result.critique.grounding >= 0.85
    assert result.citations == ISO_EVIDENCE


async def test_runtime_escalates_ungrounded_and_flywheel_overrides():
    fabricated = "Our spaceship fleet orbits Jupiter every fortnight."
    core = AgentCore(generator=Generator(provider=StubProvider(canned=fabricated)))
    req = Requirement(id="B1", text="Describe your QMS.", context=ISO_EVIDENCE, topic="qms")

    result = await core.run(req, tenant="acme")
    assert result.decision is Decision.human_review

    # A reviewer approves a grounded answer; it becomes trusted ground truth for the topic.
    await core.record_feedback(req, tenant="acme", approved_text=ISO_EVIDENCE[0])
    assert await core.verified.get("acme", "qms") == ISO_EVIDENCE
