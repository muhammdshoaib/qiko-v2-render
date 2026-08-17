"""Tests for the per-agent Intelligence Worker router."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.agents.service import Agent
from app.modules.intelligence.catalog import SourceCatalog
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
