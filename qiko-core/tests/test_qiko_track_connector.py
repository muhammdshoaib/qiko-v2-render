"""Tests for the Qiko Track Intelligence Worker connector."""
from __future__ import annotations

import socket
from datetime import datetime, timezone

import httpx
import pytest

from app.core.config import get_settings
from app.modules.intelligence.connectors import QikoTrackConnector
from app.modules.intelligence.models import InMemorySignalStore


def _public_resolver(host: str, port: int, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def _private_resolver(host: str, port: int, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]


def _context_response() -> dict:
    return {
        "actor": {"name": "Razvan Baba", "email": "razvan@qiko.ai", "role": "owner",
                  "scopes": ["read", "write"]},
        "projects": [
            {"key": "QIW", "name": "Qiko Intelligence Worker", "kind": "internal", "openTickets": 5},
        ],
    }


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _allow_test_host(monkeypatch):
    monkeypatch.setattr(get_settings(), "qiko_track_api_allowlist", ["http://testserver"])


@pytest.mark.asyncio
async def test_verify_returns_context_on_valid_token():
    def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer qt-valid"
        assert request.url.path == "/api/v1/context"
        return httpx.Response(200, json=_context_response())

    connector = QikoTrackConnector(transport=_transport(handler), resolver=_public_resolver)
    result = await connector.verify(
        config={"base_url": "http://testserver", "project_keys": ["QIW"]},
        credential="qt-valid",
    )
    assert result["ok"] is True
    assert result["actor"] == {"name": "Razvan Baba", "email": "razvan@qiko.ai",
                               "role": "owner", "scopes": ["read", "write"]}
    assert result["scopes"] == ["read", "write"]
    assert result["projects"] == [{"key": "QIW", "name": "Qiko Intelligence Worker"}]


@pytest.mark.asyncio
async def test_verify_reports_invalid_token():
    def handler(request: httpx.Request):
        return httpx.Response(401, json={"error": "unauthorized"})

    connector = QikoTrackConnector(transport=_transport(handler), resolver=_public_resolver)
    result = await connector.verify(
        config={"base_url": "http://testserver", "project_keys": ["QIW"]},
        credential="qt-invalid",
    )
    assert result["ok"] is False
    assert "token" in result["error"].lower() or "unauthorized" in result["error"].lower()


@pytest.mark.asyncio
async def test_verify_rejects_private_host_ssrf():
    connector = QikoTrackConnector(resolver=_private_resolver)
    result = await connector.verify(
        config={"base_url": "http://internal.corp", "project_keys": ["QIW"]},
        credential="qt-valid",
    )
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_verify_rejects_host_outside_allowlist():
    connector = QikoTrackConnector(resolver=_public_resolver)
    result = await connector.verify(
        config={"base_url": "http://evil.example", "project_keys": ["QIW"]},
        credential="qt-valid",
    )
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_verify_reports_missing_base_url_and_project_keys():
    connector = QikoTrackConnector(resolver=_public_resolver)
    result = await connector.verify(config={}, credential="qt-valid")
    assert result["ok"] is False
    assert "project" in result["error"].lower()


@pytest.mark.asyncio
async def test_fetch_since_is_callable_after_verify():
    """Smoke test that the connector exposes fetch_since for the HistoryStrategy in leg 2."""
    connector = QikoTrackConnector(resolver=_public_resolver)
    signals = await connector.fetch_since(
        config={"base_url": "http://testserver", "project_keys": ["QIW"]},
        credential="qt-valid",
        since=datetime.now(timezone.utc),
        signal_store=InMemorySignalStore(),
    )
    assert isinstance(signals, list)
