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
async def test_verify_reports_missing_project_keys():
    connector = QikoTrackConnector(resolver=_public_resolver)
    result = await connector.verify(config={"base_url": "http://testserver"}, credential="qt-valid")
    assert result["ok"] is False
    assert "project" in result["error"].lower()


@pytest.mark.asyncio
async def test_fetch_since_emits_created_for_new_ticket():
    store = InMemorySignalStore()

    def handler(request: httpx.Request):
        if request.url.path == "/api/v1/tickets":
            return httpx.Response(200, json={"tickets": [
                {"key": "QIW-1005", "title": "Connector", "project": "QIW", "status": "IN_PROGRESS",
                 "isBlocked": False, "implementer": "Razvan Baba", "comments": 0},
            ]})
        if request.url.path == "/api/v1/tickets/QIW-1005":
            return httpx.Response(200, json={
                "key": "QIW-1005", "title": "Connector", "project": {"key": "QIW"},
                "status": "IN_PROGRESS", "isBlocked": False, "implementer": "Razvan Baba",
                "createdAt": "2026-08-15T05:50:54.160Z", "updatedAt": "2026-08-18T08:22:09.049Z",
                "comments": [], "activity": [],
            })
        return httpx.Response(404)

    connector = QikoTrackConnector(transport=_transport(handler), resolver=_public_resolver)
    signals = await connector.fetch_since(
        config={"base_url": "http://testserver", "project_keys": ["QIW"]},
        credential="qt-valid",
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tenant="t1", agent_id="w1",
        signal_store=store,
    )
    assert len(signals) == 1
    assert signals[0].kind == "ticket_created"
    assert signals[0].ref == "QIW-1005"
    assert signals[0].container == "QIW"
    assert signals[0].source == "qiko_track"


@pytest.mark.asyncio
async def test_fetch_since_emits_moved_on_status_change():
    store = InMemorySignalStore()
    created = datetime(2026, 8, 15, 5, 50, 54, tzinfo=timezone.utc)
    await store.add(_qiko_track_signal(
        ref="QIW-1005", kind="ticket_created", occurred_at=created,
        meta={"state": {"status": "TODO", "blocked": False, "implementer": "", "comments": 0}}))

    def handler(request: httpx.Request):
        if request.url.path == "/api/v1/tickets":
            return httpx.Response(200, json={"tickets": [
                {"key": "QIW-1005", "title": "Connector", "project": "QIW", "status": "IN_PROGRESS",
                 "isBlocked": False, "implementer": "", "comments": 0},
            ]})
        if request.url.path == "/api/v1/tickets/QIW-1005":
            return httpx.Response(200, json={
                "key": "QIW-1005", "title": "Connector", "project": {"key": "QIW"},
                "status": "IN_PROGRESS", "isBlocked": False, "implementer": "",
                "createdAt": "2026-08-15T05:50:54.160Z", "updatedAt": "2026-08-18T08:22:09.049Z",
                "comments": [],
                "activity": [
                    {"actor": "Razvan Baba", "verb": "ticket.moved", "field": "status",
                     "from": "TODO", "to": "IN_PROGRESS", "at": "2026-08-18T08:22:09.054Z"},
                ],
            })
        return httpx.Response(404)

    connector = QikoTrackConnector(transport=_transport(handler), resolver=_public_resolver)
    signals = await connector.fetch_since(
        config={"base_url": "http://testserver", "project_keys": ["QIW"]},
        credential="qt-valid",
        since=created,
        tenant="t1", agent_id="w1",
        signal_store=store,
    )
    moved = [s for s in signals if s.kind == "ticket_moved"]
    assert len(moved) == 1
    assert moved[0].ref == "QIW-1005"
    assert moved[0].meta["from_status"] == "TODO"
    assert moved[0].meta["to_status"] == "IN_PROGRESS"
    assert moved[0].actor == "Razvan Baba"


@pytest.mark.asyncio
async def test_fetch_since_emits_blocked_and_moved_for_simultaneous_changes():
    store = InMemorySignalStore()
    created = datetime(2026, 8, 15, 5, 50, 54, tzinfo=timezone.utc)
    await store.add(_qiko_track_signal(
        ref="QIW-1005", kind="ticket_created", occurred_at=created,
        meta={"state": {"status": "TODO", "blocked": False, "implementer": "", "comments": 0}}))

    def handler(request: httpx.Request):
        if request.url.path == "/api/v1/tickets":
            return httpx.Response(200, json={"tickets": [
                {"key": "QIW-1005", "title": "Connector", "project": "QIW", "status": "IN_PROGRESS",
                 "isBlocked": True, "implementer": "", "comments": 0},
            ]})
        if request.url.path == "/api/v1/tickets/QIW-1005":
            return httpx.Response(200, json={
                "key": "QIW-1005", "title": "Connector", "project": {"key": "QIW"},
                "status": "IN_PROGRESS", "isBlocked": True, "blockedReason": "waiting for API",
                "implementer": "", "createdAt": "2026-08-15T05:50:54.160Z",
                "updatedAt": "2026-08-18T08:22:09.049Z", "comments": [],
                "activity": [
                    {"actor": "Razvan Baba", "verb": "ticket.moved", "field": "status",
                     "from": "TODO", "to": "IN_PROGRESS", "at": "2026-08-18T08:22:09.054Z"},
                    {"actor": "Razvan Baba", "verb": "ticket.updated", "field": "blocked",
                     "from": "false", "to": "true", "at": "2026-08-18T08:22:09.055Z"},
                ],
            })
        return httpx.Response(404)

    connector = QikoTrackConnector(transport=_transport(handler), resolver=_public_resolver)
    signals = await connector.fetch_since(
        config={"base_url": "http://testserver", "project_keys": ["QIW"]},
        credential="qt-valid",
        since=created,
        tenant="t1", agent_id="w1",
        signal_store=store,
    )
    assert {s.kind for s in signals} == {"ticket_moved", "ticket_blocked"}


@pytest.mark.asyncio
async def test_fetch_since_is_idempotent_on_repeated_sweep():
    store = InMemorySignalStore()
    created = datetime(2026, 8, 15, 5, 50, 54, tzinfo=timezone.utc)

    def handler(request: httpx.Request):
        if request.url.path == "/api/v1/tickets":
            return httpx.Response(200, json={"tickets": [
                {"key": "QIW-1005", "title": "Connector", "project": "QIW", "status": "TODO",
                 "isBlocked": False, "implementer": "", "comments": 0},
            ]})
        if request.url.path == "/api/v1/tickets/QIW-1005":
            return httpx.Response(200, json={
                "key": "QIW-1005", "title": "Connector", "project": {"key": "QIW"},
                "status": "TODO", "isBlocked": False, "implementer": "",
                "createdAt": "2026-08-15T05:50:54.160Z", "updatedAt": "2026-08-15T05:50:54.160Z",
                "comments": [], "activity": [],
            })
        return httpx.Response(404)

    connector = QikoTrackConnector(transport=_transport(handler), resolver=_public_resolver)
    for _ in range(2):
        signals = await connector.fetch_since(
            config={"base_url": "http://testserver", "project_keys": ["QIW"]},
            credential="qt-valid",
            since=created,
            tenant="t1", agent_id="w1",
            signal_store=store,
        )
        assert len(signals) == 1


def _qiko_track_signal(*, ref: str, kind: str, occurred_at: datetime, meta: dict):
    from app.modules.intelligence.models import Signal
    return Signal(
        tenant="t1", agent_id="w1", source="qiko_track", kind=kind,
        external_id=f"{ref}:{kind}:{occurred_at.isoformat()}",
        container="QIW", actor="", title="", body="",
        occurred_at=occurred_at, ref=ref, meta=meta,
    )
