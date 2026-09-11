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
from app.modules.intelligence.qiko_track_client import QikoTrackClient
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
            description="Workspace messages.")
        catalog.register(
            key="github", name="GitHub", connector=GitHubConnector(),
            description="Code, pull requests and CI.")
        catalog.register(
            key="qiko_track", name="Qiko Track", connector=QikoTrackConnector(),
            description="Tickets, comments and blockers.")
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
        "description": "Workspace messages.",
        "pollable": False, "connected": False, "configured": True,
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


def test_slack_is_connected_when_installation_exists(client):
    from app.modules.channels.slack_oauth import SlackInstallation

    client.app.state.slack_oauth.store.save(SlackInstallation(
        team_id="T1", bot_token="xoxb-fake", bot_user_id="U999",
        tenant="intelco", worker_id="w1"))

    r = client.get("/api/v1/intelligence/agents/w1/sources", cookies=C)
    assert r.status_code == 200
    sources = {s["key"]: s for s in r.json()}
    assert sources["slack"]["connected"] is True

    r = client.get("/api/v1/intelligence/agents/w1/sources/slack/connection", cookies=C)
    assert r.status_code == 200
    assert r.json()["connected"] is True
    assert r.json()["team_id"] == "T1"


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


def test_upload_document_requires_auth(client):
    r = client.post("/api/v1/intelligence/agents/w1/documents")
    assert r.status_code == 401


def test_upload_document_rejects_unsupported_extension(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/documents",
        cookies=C,
        files={"file": ("bad.exe", b"data", "application/octet-stream")},
    )
    assert r.status_code == 422


def test_upload_document_and_delete(client):
    content = b"This is the QIKO-1234 brief for the intelligence worker."
    r = client.post(
        "/api/v1/intelligence/agents/w1/documents",
        cookies=C,
        files={"file": ("brief.txt", content, "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "brief.txt"
    assert body["status"] == "ready"
    assert body["size"] == len(content)
    doc_id = body["doc_id"]

    r = client.get("/api/v1/intelligence/agents/w1/documents", cookies=C)
    assert r.status_code == 200
    assert any(d["doc_id"] == doc_id for d in r.json())

    r = client.delete(f"/api/v1/intelligence/agents/w1/documents/{doc_id}", cookies=C)
    assert r.status_code == 200

    r = client.get("/api/v1/intelligence/agents/w1/documents", cookies=C)
    assert not any(d["doc_id"] == doc_id for d in r.json())


def test_get_metrics_returns_qiko_track_project_metrics(client, monkeypatch):
    def _fake_for_projects(self, project_keys, *, window="30d", sprint=None):
        return {
            "QIW": {
                "available": True,
                "window": {"key": "14d", "from": "2026-08-01T00:00:00Z", "to": "2026-08-15T00:00:00Z"},
                "throughput": {"tickets": 3, "points": 8, "unestimated": 0, "ticketsPerWeek": 1.5, "pointsPerWeek": 4.0, "completeWeeks": 2},
            },
        }

    class FakeMetricsService:
        def __init__(self, base_url: str, token: str, ttl_seconds: float = 60.0):
            pass
        async def for_projects(self, project_keys, *, window="30d", sprint=None):
            return _fake_for_projects(self, project_keys, window=window, sprint=sprint)

    monkeypatch.setattr("app.modules.intelligence.router.MetricsService", FakeMetricsService)

    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/qiko_track",
        json={"token": "qt-token", "project_keys": ["QIW"], "base_url": "https://track.qiko.ai"},
        cookies=C,
    )
    assert r.status_code == 200

    r = client.get("/api/v1/intelligence/agents/w1/metrics", cookies=C)
    assert r.status_code == 200
    body = r.json()
    assert body["projects"]["QIW"]["available"] is True
    assert body["projects"]["QIW"]["throughput"]["tickets"] == 3


def test_get_metrics_returns_empty_when_qiko_track_not_connected(client):
    r = client.get("/api/v1/intelligence/agents/w1/metrics", cookies=C)
    assert r.status_code == 200
    assert r.json()["projects"] == {}


def test_get_overview_returns_open_prs_and_ticket_rollup(client):
    from datetime import datetime, timezone
    from app.modules.intelligence.models import Signal

    asyncio.run(client.app.state.intelligence_signal_store.add(Signal(
        tenant="intelco", agent_id="w1", source="github", kind="pr_opened",
        external_id="pr-42", container="acme/repo", actor="alice",
        title="Add feature", body="", occurred_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
        ref="PR#42", url="https://github.com/acme/repo/pull/42",
    )))

    r = client.get("/api/v1/intelligence/agents/w1/overview", cookies=C)
    assert r.status_code == 200
    body = r.json()
    assert "open_prs" in body and "in_progress_tickets" in body and "developers" in body
    assert body["open_prs"][0]["ref"] == "PR#42"
    assert body["open_prs"][0]["author"] == "alice"
    assert body["developers"][0]["actor"] == "alice"


def test_get_overview_requires_auth(client):
    r = client.get("/api/v1/intelligence/agents/w1/overview")
    assert r.status_code == 401


def test_preview_qiko_track_requires_editor(client):
    r = client.get("/api/v1/intelligence/agents/w1/sources/qiko_track/preview", cookies=auth_cookies("intelco", "viewer"))
    assert r.status_code == 403


def test_preview_qiko_track_reports_service_token_unconfigured(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "qiko_track_service_token", "")
    r = client.get("/api/v1/intelligence/agents/w1/sources/qiko_track/preview", cookies=C)
    assert r.status_code == 200
    assert r.json()["service_token_configured"] is False


def test_qiko_track_auto_connect_creates_project(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "qiko_track_service_token", "qt-service-token")
    monkeypatch.setattr(get_settings(), "qiko_track_api_allowlist", ["http://testserver"])
    monkeypatch.setattr(QikoTrackClient, "_validate_url", lambda self: None)

    calls: list = []

    async def fake_list_projects(self):
        calls.append("list")
        return []

    async def fake_create_project(self, payload, *, idempotency_key=None):
        calls.append(("create", payload, idempotency_key))
        return {"id": "p1", "key": payload["key"], "name": payload["name"]}

    monkeypatch.setattr(QikoTrackClient, "list_projects", fake_list_projects)
    monkeypatch.setattr(QikoTrackClient, "create_project", fake_create_project)

    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/qiko_track",
        cookies=C,
        json={
            "auto": True,
            "project_key": "ACME1",
            "project_name": "ACME One",
            "project_kind": "INTERNAL",
            "base_url": "http://testserver",
        },
    )
    assert r.status_code == 200
    assert r.json()["connected"] is True
    assert any(call[0] == "create" and call[1]["key"] == "ACME1" for call in calls)


def test_qiko_track_auto_connect_reuses_existing_project(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "qiko_track_service_token", "qt-service-token")
    monkeypatch.setattr(get_settings(), "qiko_track_api_allowlist", ["http://testserver"])
    monkeypatch.setattr(QikoTrackClient, "_validate_url", lambda self: None)

    async def fake_list_projects(self):
        return [{"key": "ACME1", "name": "Existing", "kind": "INTERNAL"}]

    created = []

    async def fake_create_project(self, payload, *, idempotency_key=None):
        created.append(payload)
        return {"id": "p1", "key": payload["key"], "name": payload["name"]}

    monkeypatch.setattr(QikoTrackClient, "list_projects", fake_list_projects)
    monkeypatch.setattr(QikoTrackClient, "create_project", fake_create_project)

    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/qiko_track",
        cookies=C,
        json={"auto": True, "project_key": "ACME1", "project_name": "ACME One", "project_kind": "INTERNAL", "base_url": "http://testserver"},
    )
    assert r.status_code == 200
    assert r.json()["connected"] is True
    assert created == []


def test_set_source_settings_stores_and_returns_fields(client):
    client.post(
        "/api/v1/intelligence/agents/w1/sources/github",
        cookies=C,
        json={"token": "ghp_test", "repo_allowlist": ["acme/api"], "watched_branches": ["main"]},
    )
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/github/settings",
        cookies=C,
        json={"repo_allowlist": ["acme/web"], "watched_branches": ["main", "develop"]},
    )
    assert r.status_code == 200
    assert r.json()["settings"]["repo_allowlist"] == ["acme/web"]
    assert r.json()["settings"]["watched_branches"] == ["main", "develop"]

    conn = client.get("/api/v1/intelligence/agents/w1/sources/github/connection", cookies=C)
    assert conn.status_code == 200
    assert conn.json()["settings"]["repo_allowlist"] == ["acme/web"]


def test_set_source_settings_ignores_fields_for_other_source(client):
    client.post(
        "/api/v1/intelligence/agents/w1/sources/qiko_track",
        cookies=C,
        json={"token": "qt_token", "project_keys": ["QIW"], "base_url": "https://track.example.com"},
    )
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/qiko_track/settings",
        cookies=C,
        json={"project_keys": ["QIW", "PROJ-1"], "base_url": "https://track.qiko.ai", "repo_allowlist": ["should", "be", "ignored"]},
    )
    assert r.status_code == 200
    assert r.json()["settings"]["project_keys"] == ["QIW", "PROJ-1"]
    assert r.json()["settings"]["base_url"] == "https://track.qiko.ai"


def test_slack_settings_include_purposes_and_intervals(client, monkeypatch):
    from app.modules.channels.slack_oauth import SlackInstallation

    install = SlackInstallation(
        tenant="intelco", worker_id="w1", team_id="T123",
        bot_token="xoxb-test", bot_user_id="U123",
    )
    monkeypatch.setattr(
        client.app.state.slack_oauth.store, "find_for_worker",
        lambda tenant, worker_id: install,
    )

    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/slack/settings",
        cookies=C,
        json={
            "watched_channels": ["C1", "C2"],
            "purposes": ["monitor", "digest"],
            "summary_interval_minutes": 30,
            "digest_interval_minutes": 120,
            "heads_up_timeout_minutes": 15,
        },
    )
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert settings["watched_channels"] == ["C1", "C2"]
    assert settings["purposes"] == ["monitor", "digest"]
    assert settings["summary_interval_minutes"] == 30
    assert settings["digest_interval_minutes"] == 120
    assert settings["heads_up_timeout_minutes"] == 15

    conn = client.get("/api/v1/intelligence/agents/w1/sources/slack/connection", cookies=C)
    assert conn.status_code == 200
    assert conn.json()["settings"]["digest_interval_minutes"] == 120


def test_set_source_settings_rejects_unknown_source(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/sources/nope/settings",
        cookies=C,
        json={"repo_allowlist": ["acme/api"]},
    )
    assert r.status_code == 404


def test_get_discrepancies_returns_envelope_with_project_counts(client):
    r = client.get("/api/v1/intelligence/agents/w1/discrepancies", cookies=C)
    assert r.status_code == 200
    payload = r.json()
    assert "items" in payload
    assert "total" in payload
    assert "projects" in payload
    assert isinstance(payload["items"], list)


def test_get_discrepancy_digest_rejects_viewer(client):
    cookies = auth_cookies("intelco", "viewer")
    r = client.get("/api/v1/intelligence/agents/w1/discrepancies/digest?window=daily", cookies=cookies)
    assert r.status_code == 403


def test_get_discrepancy_digest_returns_heads_up_digest_or_503(client, monkeypatch):
    # By default the stub provider refuses, so we test the shape and that the
    # endpoint is wired rather than depending on a real LLM call.
    r = client.get("/api/v1/intelligence/agents/w1/discrepancies/digest?window=daily", cookies=C)
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        payload = r.json()
        assert "headline" in payload
        assert "summary" in payload
        assert "sections" in payload
