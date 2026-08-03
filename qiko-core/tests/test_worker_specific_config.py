"""build_tenant_worker must build a genuinely different Worker per agent_id -- otherwise every
worker in a tenant (an RFP requirement-answering worker, a pre-sales content-writing worker, ...)
silently shares one identical configuration, which defeats the point of having separate agents."""
from types import SimpleNamespace

from app.core.deps import build_tenant_worker
from app.modules.agents.service import Agent, InMemoryAgentStore


def _fake_request(agents_store: InMemoryAgentStore) -> SimpleNamespace:
    state = SimpleNamespace(agents=agents_store, knowledge=SimpleNamespace())
    return SimpleNamespace(app=SimpleNamespace(state=state))


async def test_build_tenant_worker_without_agent_id_uses_generic_defaults():
    store = InMemoryAgentStore()
    request = _fake_request(store)
    worker = await build_tenant_worker(request, "acme")
    assert worker.config.system_prompt is None
    assert worker.config.name == "w-acme"


async def test_build_tenant_worker_applies_the_specific_agents_own_config():
    store = InMemoryAgentStore()
    presales = Agent(id="presales1", tenant="acme", name="Pre Sales Writer Worker", config={
        "system_prompt": "You are a pre-sales writer.", "gate_threshold": 0.6, "retrieval_k": 8,
    })
    await store.add(presales)
    request = _fake_request(store)

    worker = await build_tenant_worker(request, "acme", agent_id="presales1")
    assert worker.config.system_prompt == "You are a pre-sales writer."
    assert worker.config.gate_threshold == 0.6
    assert worker.config.retrieval_k == 8
    assert worker.agent.generator.system_prompt == "You are a pre-sales writer."
    assert worker.agent.threshold == 0.6


async def test_two_agents_in_the_same_tenant_get_independent_configs():
    store = InMemoryAgentStore()
    await store.add(Agent(id="a1", tenant="acme", name="Tender Assistant",
                          config={"system_prompt": "You answer tender requirements."}))
    await store.add(Agent(id="a2", tenant="acme", name="Pre Sales Writer",
                          config={"system_prompt": "You write pre-sales content."}))
    request = _fake_request(store)

    w1 = await build_tenant_worker(request, "acme", agent_id="a1")
    w2 = await build_tenant_worker(request, "acme", agent_id="a2")
    assert w1.config.system_prompt == "You answer tender requirements."
    assert w2.config.system_prompt == "You write pre-sales content."
    assert w1.config.system_prompt != w2.config.system_prompt


async def test_build_tenant_worker_keeps_legacy_generic_fallback_for_internal_callers():
    store = InMemoryAgentStore()
    request = _fake_request(store)
    worker = await build_tenant_worker(request, "acme", agent_id="does-not-exist")
    assert worker.config.system_prompt is None


async def test_worker_without_prompt_synthesizes_persona_from_train_config():
    # The Train wizard writes expertise/tone/full_name but no system_prompt; the worker must still
    # answer in its OWN voice, not the generic bid-writer default (QIK-315).
    store = InMemoryAgentStore()
    await store.add(Agent(id="support1", tenant="acme", name="Support Bot", config={
        "full_name": "Ava", "title": "Customer Support Lead", "expertise": "billing and refunds",
        "tone": "warm and concise",
    }))
    request = _fake_request(store)
    worker = await build_tenant_worker(request, "acme", agent_id="support1")
    sp = worker.config.system_prompt
    assert sp and "Ava" in sp and "billing and refunds" in sp and "warm and concise" in sp
    assert "bid-response writer" not in sp  # not the generic default identity


async def test_explicit_system_prompt_wins_over_synthesis():
    store = InMemoryAgentStore()
    await store.add(Agent(id="x", tenant="acme", name="X", config={
        "system_prompt": "You are X.", "expertise": "ignored when explicit prompt set",
    }))
    request = _fake_request(store)
    worker = await build_tenant_worker(request, "acme", agent_id="x")
    assert worker.config.system_prompt == "You are X."


async def test_persona_worker_still_enforces_json_output_contract():
    # A persona replaces only the identity; the JSON output contract is always appended, so the
    # gate still gets structured confidence/gaps.
    from app.modules.agentcore.generator import SYSTEM, _OUTPUT_CONTRACT, Generator

    default = Generator(provider=object())
    assert default.system == SYSTEM  # no persona -> unchanged default prompt
    persona = Generator(provider=object(), system_prompt="You are Ava, a support agent.")
    assert persona.system.startswith("You are Ava, a support agent.")
    assert _OUTPUT_CONTRACT in persona.system  # contract always enforced
