"""Tests for the per-agent Intelligence Worker router."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.agents.service import Agent
from app.modules.intelligence.catalog import SourceCatalog
from app.modules.intelligence.connectors import GitHubConnector, QikoTrackConnector
from tests.helpers import auth_cookies


C = auth_cookies("intelco", "owner")


def _seed_worker(client, tenant="intelco", agent_id="w1"):
    if asyncio.run(client.app.state.agents.get(tenant, agent_id)) is None:
        asyncio.run(client.app.state.agents.store.add(
            Agent(id=agent_id, tenant=tenant, name="Worker")))


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        _seed_worker(c)
        catalog = SourceCatalog()
        catalog.register(
            key="slack", name="Slack", connector=None,
            description="Slack workspace messages via the Events API (push).")
        catalog.register(
            key="github", name="GitHub", connector=GitHubConnector(),
            description="Repository commits, pull requests, reviews and CI status.")
        catalog.register(
            key="qiko_track", name="Qiko Track", connector=QikoTrackConnector(),
            description="Tickets, transitions, comments and blocked flags.")
        connector = _demo_connector()
        catalog.register(
            key="demo", name="Demo", connector=connector,
            description="Demo connector for verify tests.")
        c.app.state.intelligence_catalog = catalog
        yield c


def _demo_connector():
    connector = type("DemoConnector", (), {})()
    connector.key = "demo"
    connector.verify = AsyncMock(return_value={"ok": True, "source": "demo"})
    connector.fetch_since = AsyncMock(return_value=[])
    return connector


def test_list_sources_requires_auth(client):
    r = client.get("/api/v1/intelligence/agents/w1/sources")
    assert r.status_code == 401


def test_list_sources_returns_catalog(client):
    r = client.get("/api/v1/intelligence/agents/w1/sources", cookies=C)
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()}
    assert "slack" in keys
    assert "demo" in keys


def test_get_source(client):
    r = client.get("/api/v1/intelligence/agents/w1/sources/slack", cookies=C)
    assert r.status_code == 200
    assert r.json() == {
        "key": "slack", "name": "Slack",
        "description": "Slack workspace messages via the Events API (push).",
        "pollable": False, "connected": False,
    }


def test_get_unknown_source(client):
    r = client.get("/api/v1/intelligence/agents/w1/sources/nope", cookies=C)
    assert r.status_code == 404


def test_verify_source(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/demo/verify",
        json={"config": {"team_id": "T1"}, "credential": "x"},
        cookies=C,
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "source": "demo"}


def test_verify_source_forbids_viewer(client):
    viewer = auth_cookies("intelco", "viewer")
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/demo/verify",
        json={"config": {}, "credential": "x"},
        cookies=viewer,
    )
    assert r.status_code == 403


def test_verify_unknown_source(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/nope/verify",
        json={"config": {}, "credential": "x"},
        cookies=C,
    )
    assert r.status_code == 404


def test_verify_source_without_connector(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/slack/verify",
        json={"config": {}, "credential": "x"},
        cookies=C,
    )
    assert r.status_code == 404


def test_github_connect_and_disconnect(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/github",
        json={"token": "ghp-testtoken", "repo_allowlist": ["owner/repo"]},
        cookies=C,
    )
    assert r.status_code == 200
    assert r.json()["connected"] is True

    r = client.get("/api/v1/intelligence/agents/w1/sources/github/connection", cookies=C)
    assert r.status_code == 200
    assert r.json()["token_masked"].startswith("ghp-")
    assert r.json()["repo_allowlist"] == ["owner/repo"]
    assert r.json()["connected"] is True

    r = client.delete("/api/v1/intelligence/agents/w1/sources/github", cookies=C)
    assert r.status_code == 200
    assert r.json()["disconnected"] is True

    r = client.get("/api/v1/intelligence/agents/w1/sources/github/connection", cookies=C)
    assert r.json()["connected"] is False


def test_qiko_track_connect_test_and_disconnect(client):
    from datetime import datetime, timezone
    from app.modules.intelligence.models import Signal

    async def _fake_verify(*, config, credential):
        return {"ok": True, "actor": {"name": "A"}, "scopes": ["read"], "projects": config.get("project_keys", [])}

    async def _fake_fetch_since(*, config, credential, since, tenant, agent_id, signal_store):
        return [Signal(
            tenant=tenant, agent_id=agent_id, source="qiko_track", kind="ticket_created",
            external_id="PROJ-1:PROJ-1:created:2026-08-18T00:00:00+00:00",
            container="PROJ-1", actor="A", title="PROJ-1 created", body="",
            occurred_at=datetime(2026, 8, 18, tzinfo=timezone.utc), ref="PROJ-1",
        )]

    connector = client.app.state.intelligence_catalog.connector_for("qiko_track")
    connector.verify = _fake_verify
    connector.fetch_since = _fake_fetch_since

    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/qiko_track",
        json={"token": "qt-token", "project_keys": ["PROJ-1"], "base_url": "https://track.qiko.ai"},
        cookies=C,
    )
    assert r.status_code == 200
    assert r.json()["connected"] is True
    assert r.json()["ingested"]["added"] == 1

    r = client.get("/api/v1/intelligence/agents/w1/sources/qiko_track/connection", cookies=C)
    assert r.status_code == 200
    assert r.json()["project_keys"] == ["PROJ-1"]
    assert r.json()["connected"] is True

    r = client.post("/api/v1/intelligence/agents/w1/sources/qiko_track/test", cookies=C)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.delete("/api/v1/intelligence/agents/w1/sources/qiko_track", cookies=C)
    assert r.status_code == 200


def test_slack_connect_returns_oauth_url(client):
    r = client.post("/api/v1/intelligence/agents/w1/sources/slack", cookies=C)
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://slack.com/oauth/v2/authorize")


def test_slack_watched_channels_are_stored(client):
    from app.modules.channels.slack_oauth import SlackInstallation

    client.app.state.slack_oauth.store.save(SlackInstallation(
        team_id="T1", bot_token="xoxb-fake", bot_user_id="U999",
        tenant="intelco", worker_id="w1"))
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/slack/channels",
        json={"channel_ids": ["C123", "C456"]},
        cookies=C,
    )
    assert r.status_code == 200
    assert r.json()["watched_channels"] == ["C123", "C456"]

    r = client.get("/api/v1/intelligence/agents/w1/sources/slack/channels", cookies=C)
    assert r.status_code == 200
    assert r.json()["watched_channels"] == ["C123", "C456"]
