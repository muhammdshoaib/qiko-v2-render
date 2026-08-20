import asyncio

from fastapi.testclient import TestClient

from app.modules.agents.service import Agent
from app.modules.intelligence.orchestration import Pipeline, PipelineConfig
from tests.helpers import auth_cookies


class _FakeTaskQueue:
    """Not an EagerTaskQueue, so the route takes the arq branch and only serialisable ids are queued."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def enqueue(self, name: str, **kwargs):
        self.calls.append((name, kwargs))


def _seed_worker(client: TestClient, tenant: str = "acme", agent_id: str = "w1") -> None:
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=agent_id, tenant=tenant, name="Pipeline Worker")))


def test_create_pipeline_run_persists_and_enqueues(client):
    _seed_worker(client)
    queue = _FakeTaskQueue()
    client.app.state.task_queue = queue
    cookies = auth_cookies("acme", "owner")

    r = client.post(
        "/api/v1/intelligence/agents/w1/pipeline/runs",
        json={"subject": "What does ACME do?", "facets": ["products", "market", "products"]},
        cookies=cookies,
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["run_id"]
    assert data["tenant"] == "acme"
    assert data["agent_id"] == "w1"
    assert data["subject"] == "What does ACME do?"
    assert data["facets"] == ["products", "market"]  # deduped and capped
    assert data["status"]["scout"] == "pending"
    assert data["verdict"] is None
    assert queue.calls == [
        ("run_intelligence_pipeline", {"tenant": "acme", "agent_id": "w1", "run_id": data["run_id"]}),
    ]

    # GET returns the persisted run
    r2 = client.get(f"/api/v1/intelligence/agents/w1/pipeline/runs/{data['run_id']}", cookies=cookies)
    assert r2.status_code == 200
    assert r2.json()["run_id"] == data["run_id"]


def test_get_pipeline_run_404_for_unknown(client):
    cookies = auth_cookies("acme", "owner")
    r = client.get("/api/v1/intelligence/agents/w1/pipeline/runs/does-not-exist", cookies=cookies)
    assert r.status_code == 404


def test_create_pipeline_run_404_for_unknown_agent(client):
    cookies = auth_cookies("acme", "owner")
    r = client.post(
        "/api/v1/intelligence/agents/unknown/pipeline/runs",
        json={"subject": "X", "facets": ["y"]},
        cookies=cookies,
    )
    assert r.status_code == 404


def test_resume_pipeline_run_enqueues_existing_run(client):
    _seed_worker(client)
    queue = _FakeTaskQueue()
    client.app.state.task_queue = queue
    cookies = auth_cookies("acme", "owner")

    # seed a run directly in the store
    config = PipelineConfig(tenant="acme", agent_id="w1", subject="S", facets=["f1"])
    run = Pipeline.new_run(config, run_id="run-123")
    asyncio.run(client.app.state.pipeline_run_store.add(run))

    r = client.post(
        "/api/v1/intelligence/agents/w1/pipeline/runs/run-123/resume",
        cookies=cookies,
    )

    assert r.status_code == 200, r.text
    assert r.json()["run_id"] == "run-123"
    assert queue.calls == [
        ("run_intelligence_pipeline", {"tenant": "acme", "agent_id": "w1", "run_id": "run-123"}),
    ]
