import pytest
from pydantic import BaseModel

from app.modules.agentcore import critic, gate
from app.modules.agentcore.flywheel import InMemoryVerifiedStore
from app.modules.agentcore.generator import Generator
from app.modules.agentcore.models import Critique, Decision, Requirement
from app.modules.agentcore.runtime import AgentCore
from app.modules.agentcore.tools import ToolError, ToolRegistry
from app.modules.ai.gateway import StubProvider

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
