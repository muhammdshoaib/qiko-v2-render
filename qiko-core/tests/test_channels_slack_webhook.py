"""The Slack Events API webhook: signature, replay window, kill switch and tenant resolution."""
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

SECRET = "test-signing-secret"


def _sign(body: bytes, ts: str, secret: str = SECRET) -> str:
    base = b"v0:" + ts.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def _payload(event: dict, *, event_id: str = "Ev123", team_id: str = "T123") -> bytes:
    return json.dumps({
        "team_id": team_id,
        "api_app_id": "A123",
        "event": event,
        "type": "event_callback",
        "event_id": event_id,
        "event_time": 1503435956,
    }).encode()


def _message_event(text: str = "we need to fix the pricing page #action", **overrides) -> dict:
    return {"type": "message", "team": "T123", "channel": "C456", "channel_type": "channel",
            "user": "U789", "text": text, "ts": "1503435956.000247", **overrides}


def _post(client: TestClient, body: bytes, *, ts: str | None = None,
          signature: str | None = None):
    ts = ts if ts is not None else str(int(time.time()))
    return client.post(
        "/api/v1/channels/slack/webhook",
        content=body,
        headers={"X-Slack-Signature": signature if signature is not None else _sign(body, ts),
                 "X-Slack-Request-Timestamp": ts,
                 "Content-Type": "application/json"},
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(get_settings(), "slack_signing_secret", SECRET)
    monkeypatch.setattr(get_settings(), "slack_capture_enabled", True)
    monkeypatch.setattr(get_settings(), "slack_digest_interval_minutes", 60)
    app = create_app()
    app.state.slack_oauth.store.save(SlackInstallation(
        team_id="T123", bot_token="xoxb-fake", bot_user_id="U999",
        tenant="tenant-1", worker_id="worker-1"))
    app.state.slack_digest_scheduler.message_store = InMemorySlackChannelStore()

    async def fake_enqueue(name, *, defer_by=None, **kwargs):
        app.state.enqueued.append((name, defer_by, kwargs))
        return Mock()

    app.state.enqueued = []
    app.state.slack_digest_scheduler.task_queue = Mock(enqueue=fake_enqueue)
    return TestClient(app)


def _stored(client: TestClient) -> list:
    return client.app.state.slack_digest_scheduler.message_store._messages


def test_url_verification_returns_the_challenge(client):
    body = b'{"type":"url_verification","challenge":"abc123"}'
    resp = _post(client, body)
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "abc123"}


def test_message_is_stored_and_a_digest_is_scheduled(client):
    resp = _post(client, _payload(_message_event()))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    messages = _stored(client)
    assert len(messages) == 1
    stored = messages[0]
    assert stored.tenant == "tenant-1"
    assert stored.team_id == "T123"
    assert stored.channel_id == "C456"
    assert stored.flagged is True
    assert "action" in stored.tags

    assert len(client.app.state.enqueued) == 1
    name, defer_by, kwargs = client.app.state.enqueued[0]
    assert name == "generate_slack_digest"
    assert kwargs == {"tenant": "tenant-1", "agent_id": "worker-1", "team_id": "T123",
                      "channel_id": "C456", "enterprise_id": None}
    assert defer_by is not None


def test_app_mention_is_captured_and_flagged(client):
    """A real app_mention carries no channel_type, so the handler must not require one."""
    event = {"type": "app_mention", "team": "T123", "channel": "C456", "user": "U789",
             "text": "<@U999> remember to update the launch date", "ts": "1503435957.000248"}
    resp = _post(client, _payload(event, event_id="Ev124"))
    assert resp.status_code == 200

    messages = _stored(client)
    assert len(messages) == 1
    assert messages[0].flagged is True
    # The bot mention itself is stripped from what we persist.
    assert messages[0].text == "remember to update the launch date"


def test_an_invalid_signature_is_refused_without_explaining_why(client):
    resp = _post(client, _payload(_message_event()), signature="v0=deadbeef")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"
    assert _stored(client) == []


def test_a_stale_but_correctly_signed_request_is_refused(client):
    """The replay control. The signature is valid forever, so the timestamp has to be checked."""
    stale = str(int(time.time()) - 600)
    body = _payload(_message_event())
    resp = _post(client, body, ts=stale, signature=_sign(body, stale))
    assert resp.status_code == 403
    assert _stored(client) == []


def test_a_non_integer_timestamp_fails_closed(client):
    body = _payload(_message_event())
    resp = _post(client, body, ts="not-a-timestamp", signature=_sign(body, "not-a-timestamp"))
    assert resp.status_code == 403


def test_capture_is_disabled_by_default(monkeypatch):
    """Setting a signing secret must not by itself start persisting a customer's conversations."""
    monkeypatch.setattr(get_settings(), "slack_signing_secret", SECRET)
    monkeypatch.setattr(get_settings(), "slack_capture_enabled", False)
    disabled = TestClient(create_app())
    resp = _post(disabled, _payload(_message_event()))
    assert resp.status_code == 501


def test_the_kill_switch_is_not_a_configuration_oracle(monkeypatch):
    """An unsigned caller must not be able to tell capture-disabled (501) from enabled (403)."""
    monkeypatch.setattr(get_settings(), "slack_signing_secret", SECRET)
    monkeypatch.setattr(get_settings(), "slack_capture_enabled", False)
    disabled = TestClient(create_app())
    resp = _post(disabled, _payload(_message_event()), signature="v0=deadbeef")
    assert resp.status_code == 403


def test_the_enterprise_id_is_captured_for_the_worker(client):
    """It is half the installation key, so the worker cannot resolve the token without it."""
    body = json.dumps({
        "team_id": "T123", "enterprise_id": "E9", "api_app_id": "A123",
        "event": _message_event(), "type": "event_callback", "event_id": "Ev-ent",
        "event_time": 1503435956,
    }).encode()
    # The install is non-enterprise, so an enterprise-scoped event must not resolve to it.
    assert _post(client, body).json() == {"ok": True, "dropped": True}

    client.app.state.slack_oauth.store.save(SlackInstallation(
        team_id="T123", bot_token="xoxb-grid", bot_user_id="U999", enterprise_id="E9",
        tenant="tenant-1", worker_id="worker-1"))
    body2 = json.dumps({
        "team_id": "T123", "enterprise_id": "E9", "api_app_id": "A123",
        "event": _message_event(), "type": "event_callback", "event_id": "Ev-ent-2",
        "event_time": 1503435956,
    }).encode()
    assert _post(client, body2).json() == {"ok": True}
    assert _stored(client)[0].enterprise_id == "E9"
    assert client.app.state.enqueued[-1][2]["enterprise_id"] == "E9"


def test_a_duplicate_event_id_is_processed_once(client):
    body = _payload(_message_event())
    assert _post(client, body).status_code == 200
    second = _post(client, body)
    assert second.json() == {"ok": True, "duplicate": True}
    assert len(_stored(client)) == 1


def test_an_event_for_an_unknown_workspace_is_dropped(client):
    resp = _post(client, _payload(_message_event(), team_id="T-OTHER"))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "dropped": True}
    assert _stored(client) == []


def test_an_ambiguous_workspace_is_refused_rather_than_guessed(client):
    """Two tenants, one workspace: there is no correct answer, so nothing may be stored."""
    client.app.state.slack_oauth.store.save(SlackInstallation(
        team_id="T123", bot_token="xoxb-other", bot_user_id="U998",
        tenant="tenant-2", worker_id="worker-2"))
    resp = _post(client, _payload(_message_event()))
    assert resp.json() == {"ok": True, "dropped": True}
    assert _stored(client) == []


def test_an_installation_with_no_tenant_is_not_treated_as_one(monkeypatch):
    """exchange_code(save=True) can persist a tenantless install; it must not collect messages."""
    monkeypatch.setattr(get_settings(), "slack_signing_secret", SECRET)
    monkeypatch.setattr(get_settings(), "slack_capture_enabled", True)
    app = create_app()
    app.state.slack_oauth.store.save(SlackInstallation(
        team_id="T123", bot_token="xoxb-fake", bot_user_id="U999"))
    app.state.slack_digest_scheduler.message_store = InMemorySlackChannelStore()
    orphaned = TestClient(app)

    resp = _post(orphaned, _payload(_message_event()))
    assert resp.json() == {"ok": True, "dropped": True}
    assert app.state.slack_digest_scheduler.message_store._messages == []


def test_bot_messages_edits_and_dms_are_ignored(client):
    cases = [
        _message_event(bot_id="B1"),
        _message_event(subtype="message_changed"),
        _message_event(channel_type="im"),
    ]
    for i, event in enumerate(cases):
        assert _post(client, _payload(event, event_id=f"Ev-skip-{i}")).status_code == 200
    assert _stored(client) == []


def test_message_text_is_truncated_on_ingest(client):
    from app.modules.channels.slack_events import MAX_MESSAGE_CHARS

    resp = _post(client, _payload(_message_event("x" * 50_000)))
    assert resp.status_code == 200
    assert len(_stored(client)[0].text) == MAX_MESSAGE_CHARS
