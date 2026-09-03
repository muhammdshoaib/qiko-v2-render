"""Tests for GET /agents/{agent_id}/analytics -- tenant-facing usage volume, no cost."""

import asyncio
from datetime import datetime, timezone

from app.modules.agents.service import Agent
from app.modules.ai import usage as usage_module
from tests.helpers import auth_cookies

NOW = datetime.now(timezone.utc)


def _event(tenant, agent, *, cost=1_000_000, calls_in=100, calls_out=20):
    return usage_module.UsageEvent(
        tenant=tenant, agent_id=agent, model_id="anthropic.claude-sonnet-4-5", operation="generate",
        input_tokens=calls_in, output_tokens=calls_out, cost_nano_usd=cost, created_at=NOW, priced=True,
    )


def test_analytics_returns_zeroed_stats_when_the_agent_has_no_usage_yet(client):
    c = auth_cookies("analyticsco", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()

    response = client.get(f"/api/v1/agents/{agent['id']}/analytics", cookies=c)

    assert response.status_code == 200
    assert response.json() == {"calls": 0, "input_tokens": 0, "output_tokens": 0, "unpriced_calls": 0}


def test_analytics_returns_the_agents_call_and_token_counts(client):
    c = auth_cookies("analyticsco2", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()
    asyncio.run(client.app.state.ai_usage.add_many([
        _event("analyticsco2", agent["id"], calls_in=100, calls_out=20),
        _event("analyticsco2", agent["id"], calls_in=50, calls_out=10),
    ]))

    response = client.get(f"/api/v1/agents/{agent['id']}/analytics", cookies=c)

    assert response.status_code == 200
    body = response.json()
    assert body["calls"] == 2
    assert body["input_tokens"] == 150
    assert body["output_tokens"] == 30


def test_analytics_never_includes_cost(client):
    c = auth_cookies("analyticsco3", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()
    asyncio.run(client.app.state.ai_usage.add_many([_event("analyticsco3", agent["id"])]))

    response = client.get(f"/api/v1/agents/{agent['id']}/analytics", cookies=c)

    assert "cost_nano_usd" not in response.json()
    assert "cost" not in response.json()


def test_analytics_does_not_leak_another_agents_usage(client):
    c = auth_cookies("analyticsco4", "owner")
    agent_a = client.post("/api/v1/agents", json={"name": "A"}, cookies=c).json()
    asyncio.run(client.app.state.agents.store.add(Agent(id="agent-b", tenant="analyticsco4", name="B")))
    asyncio.run(client.app.state.ai_usage.add_many([_event("analyticsco4", agent_a["id"])]))

    response = client.get("/api/v1/agents/agent-b/analytics", cookies=c)

    assert response.json()["calls"] == 0


def test_analytics_404s_for_a_missing_agent(client):
    c = auth_cookies("analyticsco5", "owner")
    response = client.get("/api/v1/agents/does-not-exist/analytics", cookies=c)
    assert response.status_code == 404


def test_analytics_does_not_leak_across_tenants(client):
    c1 = auth_cookies("analyticsco6", "owner")
    agent = client.post("/api/v1/agents", json={"name": "A"}, cookies=c1).json()
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=agent["id"], tenant="other-tenant", name="Same id, different tenant")
    ))
    asyncio.run(client.app.state.ai_usage.add_many([_event("analyticsco6", agent["id"])]))

    c2 = auth_cookies("other-tenant", "owner")
    response = client.get(f"/api/v1/agents/{agent['id']}/analytics", cookies=c2)

    assert response.json()["calls"] == 0
