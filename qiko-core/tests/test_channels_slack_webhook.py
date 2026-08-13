"""Tests for the Slack Events API webhook and the digest scheduler."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.modules.channels.slack_oauth import SlackInstallation
from app.modules.channels.slack_store import InMemorySlackChannelStore


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(get_settings(), "slack_signing_secret", "shh")
    monkeypatch.setattr(get_settings(), "slack_digest_interval_minutes", 60)
    app = create_app()
    installation = SlackInstallation(
        team_id="T123",
        bot_token="xoxb-fake",
        bot_user_id="U999",
        tenant="tenant-1",
        worker_id="worker-1",
    )
    app.state.slack_oauth.store.save(installation)
    app.state.slack_digest_scheduler.message_store = InMemorySlackChannelStore()
    return TestClient(app)


def _sign(secret: str, body: bytes, ts: str) -> str:
    base = f"v0:{ts}:{body.decode()}".encode()
    sig = hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return f"v0={sig}"


def test_url_verification(client):
    body = '{"type":"url_verification","challenge":"abc123"}'
    ts = str(int(time.time()))
    resp = client.post(
        "/api/v1/channels/slack/webhook",
        content=body.encode(),
        headers={
            "X-Slack-Signature": _sign("shh", body.encode(), ts),
            "X-Slack-Request-Timestamp": ts,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "abc123"}


def test_message_stored_and_scheduled(client, monkeypatch):
    queued = []

    async def fake_enqueue(name, *, defer_by=None, **kwargs):
        queued.append((name, defer_by, kwargs))
        return Mock()

    monkeypatch.setattr(client.app.state.slack_digest_scheduler, "task_queue",
                        Mock(enqueue=fake_enqueue))

    body = json.dumps({
        "token": "Jhj5dZrVaK7ZwHHjRyZWjbCt",
        "team_id": "T123",
        "api_app_id": "A123",
        "event": {
            "type": "message",
            "team": "T123",
            "channel": "C456",
            "channel_type": "channel",
            "user": "U789",
            "text": "we need to fix the pricing page #action",
            "ts": "1503435956.000247",
        },
        "type": "event_callback",
        "event_id": "Ev123",
        "event_time": 1503435956,
    })
    ts = str(int(time.time()))
    resp = client.post(
        "/api/v1/channels/slack/webhook",
        content=body.encode(),
        headers={
            "X-Slack-Signature": _sign("shh", body.encode(), ts),
            "X-Slack-Request-Timestamp": ts,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    store = client.app.state.slack_digest_scheduler.message_store
    msgs = store._messages
    assert len(msgs) == 1
    assert msgs[0].tenant == "tenant-1"
    assert msgs[0].channel_id == "C456"
    assert msgs[0].text == "we need to fix the pricing page #action"
    assert msgs[0].flagged is True
    assert "action" in msgs[0].tags

    assert len(queued) == 1
    name, defer_by, kwargs = queued[0]
    assert name == "generate_slack_digest"
    assert kwargs["tenant"] == "tenant-1"
    assert kwargs["team_id"] == "T123"
    assert kwargs["channel_id"] == "C456"
    assert defer_by is not None


def test_app_mention_sets_flagged(client, monkeypatch):
    async def fake_enqueue(name, *, defer_by=None, **kwargs):
        return Mock()

    monkeypatch.setattr(client.app.state.slack_digest_scheduler, "task_queue",
                        Mock(enqueue=fake_enqueue))

    body = json.dumps({
        "token": "Jhj5dZrVaK7ZwHHjRyZWjbCt",
        "team_id": "T123",
        "api_app_id": "A123",
        "event": {
            "type": "app_mention",
            "team": "T123",
            "channel": "C456",
            "channel_type": "channel",
            "user": "U789",
            "text": "<@U999> remember to update the launch date",
            "ts": "1503435957.000248",
        },
        "type": "event_callback",
        "event_id": "Ev124",
        "event_time": 1503435957,
    })
    ts = str(int(time.time()))
    resp = client.post(
        "/api/v1/channels/slack/webhook",
        content=body.encode(),
        headers={
            "X-Slack-Signature": _sign("shh", body.encode(), ts),
            "X-Slack-Request-Timestamp": ts,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    store = client.app.state.slack_digest_scheduler.message_store
    assert len(store._messages) == 1
    assert store._messages[0].flagged is True
    assert "remember to update the launch date" in store._messages[0].text


def test_invalid_signature_rejected(client):
    body = b'{"type":"url_verification","challenge":"x"}'
    resp = client.post(
        "/api/v1/channels/slack/webhook",
        content=body,
        headers={
            "X-Slack-Signature": "v0=bad",
            "X-Slack-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 403
