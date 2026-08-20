"""Route-level tests for the backlog proposal endpoints (QIW-1017)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.crypto import encrypt
from app.modules.agents.service import Agent
from app.modules.intelligence.orchestration import Pipeline, PipelineConfig
from tests.helpers import auth_cookies


@pytest.fixture(autouse=True)
def _allow_test_host(monkeypatch):
    monkeypatch.setattr(get_settings(), "qiko_track_api_allowlist", ["https://8.8.8.8"])


def _seed_worker(client: TestClient, tenant: str = "acme", agent_id: str = "w1") -> None:
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=agent_id, tenant=tenant, name="Research Worker")))


def _accepted_research_run(client: TestClient, run_id: str = "run-123") -> None:
    config = PipelineConfig(tenant="acme", agent_id="w1", subject="ACME", facets=["products"], kind="research")
    run = Pipeline.new_run(config, run_id=run_id)
    run.status["magistrate"] = "ready"
    run.status["outputs"]["consolidated"] = {
        "text": "ACME builds AI tools.",
        "findings": [
            {"text": "AI tools", "evidence_refs": ["doc-1"], "gaps": ""},
            {"text": "Security review is a high priority", "evidence_refs": ["doc-2"], "gaps": ""},
        ],
        "citations": ["doc-1", "doc-2"],
    }
    run.status["outputs"]["brief"] = {"accepted": True, "accepted_at": "2026-08-20T12:00:00+00:00"}
    run.verdict = "accept"
    asyncio.run(client.app.state.pipeline_run_store.add(run))


def _connect_qiko_track(client: TestClient, agent_id: str = "w1") -> None:
    asyncio.run(client.app.state.agents.update_config(
        "acme", agent_id, {
            "qiko_track_credentials_added": True,
            "qiko_track_token_encrypted": encrypt("test-token"),
            "qiko_track_project_keys": ["ACM"],
            "qiko_track_base_url": "https://8.8.8.8",
        }))




def test_get_backlog_proposal_requires_qiko_track_connection(client):
    _seed_worker(client)
    _accepted_research_run(client)
    cookies = auth_cookies("acme", "owner")

    r = client.get("/api/v1/intelligence/agents/w1/research/runs/run-123/backlog", cookies=cookies)

    assert r.status_code == 422
    assert "no Qiko Track connection" in r.json()["detail"]


def test_get_backlog_proposal_returns_epic_and_children(client):
    _seed_worker(client)
    _accepted_research_run(client)
    _connect_qiko_track(client)
    cookies = auth_cookies("acme", "owner")

    r = client.get("/api/v1/intelligence/agents/w1/research/runs/run-123/backlog", cookies=cookies)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["project_key"] == "ACM"
    assert len(data["items"]) == 3
    assert data["items"][0]["type"] == "EPIC"
    assert data["items"][0]["title"] == "ACME"
    assert data["items"][1]["parent_index"] == 0
    assert data["items"][2]["type"] == "FEATURE"


def test_create_backlog_tickets_requires_editor(client):
    _seed_worker(client)
    _accepted_research_run(client)
    _connect_qiko_track(client)
    viewer = auth_cookies("acme", "viewer")

    r = client.post(
        "/api/v1/intelligence/agents/w1/research/runs/run-123/backlog",
        json={"project_key": "ACM", "items": [{"title": "T", "description_md": "d", "type": "FEATURE"}]},
        cookies=viewer,
    )

    assert r.status_code == 403


def test_create_backlog_tickets_calls_qiko_track_and_returns_keys(client, monkeypatch):
    _seed_worker(client)
    _accepted_research_run(client)
    _connect_qiko_track(client)
    cookies = auth_cookies("acme", "owner")

    fake_service = type("FakeBacklogService", (), {})()
    fake_service.propose = lambda *a, **k: None
    fake_service.create_approved = AsyncMock(return_value=[
        {"index": 0, "key": "ACM-100", "title": "ACME"},
    ])

    monkeypatch.setattr(
        "app.modules.intelligence.router.BacklogService",
        lambda *a, **k: fake_service,
    )

    r = client.post(
        "/api/v1/intelligence/agents/w1/research/runs/run-123/backlog",
        json={
            "project_key": "ACM",
            "items": [
                {"title": "ACME", "description_md": "d", "type": "EPIC"},
            ],
        },
        cookies=cookies,
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["created"]) == 1
    assert data["created"][0]["key"] == "ACM-100"
