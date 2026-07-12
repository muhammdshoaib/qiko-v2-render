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


async def test_build_tenant_worker_falls_back_to_generic_for_unknown_agent_id():
    store = InMemoryAgentStore()
    request = _fake_request(store)
    worker = await build_tenant_worker(request, "acme", agent_id="does-not-exist")
    assert worker.config.system_prompt is None
