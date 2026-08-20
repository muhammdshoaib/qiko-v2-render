"""Route-level tests for the research brief endpoints (QIW-1016)."""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.modules.agents.service import Agent
from app.modules.intelligence.orchestration import Pipeline, PipelineConfig
from tests.helpers import auth_cookies


class _FakeTaskQueue:
    """Not an EagerTaskQueue, so the route takes the arq branch and only serialisable ids queue."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def enqueue(self, name: str, **kwargs):
        self.calls.append((name, kwargs))


def _seed_worker(client: TestClient, tenant: str = "acme", agent_id: str = "w1") -> None:
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=agent_id, tenant=tenant, name="Research Worker")))


def _completed_research_run(client: TestClient, run_id: str = "run-123") -> None:
    config = PipelineConfig(tenant="acme", agent_id="w1", subject="ACME", facets=["products"], kind="research")
    run = Pipeline.new_run(config, run_id=run_id)
    run.status["magistrate"] = "ready"
    run.status["outputs"]["consolidated"] = {
        "text": "ACME builds AI tools.",
        "findings": [
            {"text": "AI tools", "evidence_refs": ["doc-1"], "gaps": ""},
        ],
        "citations": ["doc-1"],
    }
    run.verdict = "accept"
    asyncio.run(client.app.state.pipeline_run_store.add(run))


def test_create_research_run_persists_and_enqueues(client):
    _seed_worker(client)
    queue = _FakeTaskQueue()
    client.app.state.task_queue = queue
    cookies = auth_cookies("acme", "owner")

    r = client.post(
        "/api/v1/intelligence/agents/w1/research/runs",
        json={"subject": "What does ACME do?", "facets": ["products", "market", "products"]},
        cookies=cookies,
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["run_id"]
    assert data["tenant"] == "acme"
    assert data["agent_id"] == "w1"
    assert data["subject"] == "What does ACME do?"
    assert data["facets"] == ["products", "market"]
    assert data["status"]["config"]["kind"] == "research"
    assert data["brief"]["status"] == "in_progress"
    assert queue.calls == [
        ("run_intelligence_pipeline", {"tenant": "acme", "agent_id": "w1", "run_id": data["run_id"]}),
    ]


def test_get_research_run_returns_brief(client):
    _seed_worker(client)
    _completed_research_run(client)
    cookies = auth_cookies("acme", "owner")

    r = client.get("/api/v1/intelligence/agents/w1/research/runs/run-123", cookies=cookies)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["brief"]["status"] == "draft"
    assert data["brief"]["summary"] == "ACME builds AI tools."
    assert data["brief"]["findings"][0]["text"] == "AI tools"
    assert data["brief"]["findings"][0]["evidence_refs"] == ["doc-1"]


def test_get_research_run_404_for_non_research_pipeline_run(client):
    _seed_worker(client)
    config = PipelineConfig(tenant="acme", agent_id="w1", subject="S", facets=["f1"])
    run = Pipeline.new_run(config, run_id="run-123")
    asyncio.run(client.app.state.pipeline_run_store.add(run))
    cookies = auth_cookies("acme", "owner")

    r = client.get("/api/v1/intelligence/agents/w1/research/runs/run-123", cookies=cookies)

    assert r.status_code == 404


def test_accept_research_run_ingests_ground_truth(client):
    _seed_worker(client)
    _completed_research_run(client)
    cookies = auth_cookies("acme", "owner")

    r = client.post("/api/v1/intelligence/agents/w1/research/runs/run-123/accept", cookies=cookies)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["brief"]["status"] == "accepted"

    docs = asyncio.run(client.app.state.knowledge.list_documents("acme", agent_id="w1"))
    assert any(d["doc_id"] == "research:run-123" for d in docs)

    signals = asyncio.run(client.app.state.intelligence_signal_store.list_recent(
        "acme", "w1", source="research"))
    assert len(signals) == 1
    assert signals[0].kind == "brief"
