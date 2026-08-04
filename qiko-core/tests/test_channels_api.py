import asyncio

import pytest

from app.modules.agents.service import Agent
from tests.helpers import auth_cookies


def _cookies():
    return auth_cookies("chan", "owner")


@pytest.fixture(autouse=True)
def _seed_worker(client):
    if asyncio.run(client.app.state.agents.get("chan", "w1")) is None:
        asyncio.run(client.app.state.agents.store.add(
            Agent(id="w1", tenant="chan", name="Worker")))


def _connect(client, path: str, body: dict):
    """Store a per-worker integration credential the way the Connections UI does."""
    r = client.post(f"/api/v1/agents/w1/{path}", json=body, cookies=_cookies())
    assert r.status_code == 200, r.text
    return r.json()


def test_outbound_sends(client):
    assert client.post(
        "/api/v1/channels/whatsapp/send",
        json={"to": "155", "text": "hi", "worker_id": "w1"},
        cookies=_cookies()).json()["stub"] is True
    assert client.post(
        "/api/v1/channels/gmail/send",
        json={"to": "a@invalid", "subject": "S", "body": "B", "worker_id": "w1"},
        cookies=_cookies()).json()["sent"] is True


def test_clickup_task_requires_a_per_worker_connection(client):
    # No global Qiko token is used any more: an unconfigured worker gets a clear 422, never a task
    # created in Qiko's own ClickUp.
    r = client.post("/api/v1/channels/clickup/task",
                    json={"list_id": "L", "name": "N", "worker_id": "w1"}, cookies=_cookies())
    assert r.status_code == 422 and "ClickUp" in r.json()["detail"]


def test_clickup_task_uses_the_worker_token_and_default_list(client, monkeypatch):
    calls = {}

    class FakeClickUp:
        def __init__(self, api_token=None, client=None):
            calls["token"] = api_token

        def create_task(self, list_id, name, description):
            calls["list_id"] = list_id
            return {"id": "task-1"}

    monkeypatch.setattr("app.integrations.clients.ClickUpClient", FakeClickUp)
    _connect(client, "clickup-credentials", {"api_token": "pk_secret", "default_list_id": "L-default"})
    body = client.post("/api/v1/channels/clickup/task",
                       json={"name": "N", "worker_id": "w1"}, cookies=_cookies()).json()
    assert body["id"] == "task-1"
    assert calls["token"] == "pk_secret"          # decrypted from the worker's own config
    assert calls["list_id"] == "L-default"        # falls back to the configured list


def test_outbound_requires_editor(client):
    assert client.post("/api/v1/channels/whatsapp/send", json={"to": "1", "text": "x", "worker_id": "w1"}, cookies=auth_cookies("chan", "viewer")).status_code == 403


def test_calendly_requires_a_per_worker_connection(client):
    r = client.get("/api/v1/channels/calendly/slots",
                   params={"event_type": "intro", "worker_id": "w1"}, cookies=_cookies())
    assert r.status_code == 422 and "Calendly" in r.json()["detail"]


def test_calendly_slots_and_booking_use_the_worker_token(client, monkeypatch):
    calls = {}

    class FakeCalendly:
        def __init__(self, token=None, client=None):
            calls["token"] = token

        def available_slots(self, event_type):
            calls["event_type"] = event_type
            return ["2026-07-10T09:00:00Z", "2026-07-10T10:00:00Z"]

        def create_booking(self, event_type, invitee_email, start):
            return {"booked": True}

    monkeypatch.setattr("app.integrations.clients.CalendlyClient", FakeCalendly)
    _connect(client, "calendly-credentials", {"token": "cal_secret"})
    slots = client.get("/api/v1/channels/calendly/slots",
                       params={"event_type": "intro", "worker_id": "w1"}, cookies=_cookies()).json()["slots"]
    assert len(slots) == 2 and calls["token"] == "cal_secret"
    booked = client.post("/api/v1/channels/calendly/book",
                         json={"event_type": "intro", "invitee_email": "a@invalid",
                               "start": "2026-07-10T09:00:00Z", "worker_id": "w1"}, cookies=_cookies()).json()
    assert booked["booked"] is True


def test_slack_install_and_link(client):
    assert "slack.com/oauth" in client.get("/api/v1/channels/slack/install", params={"worker_id": "w1"}, cookies=_cookies()).json()["url"]
    assert client.post("/api/v1/channels/slack/link",
                       json={"team_id": "T1", "slack_user_id": "U1", "worker_id": "w1"}, cookies=_cookies()).json()["linked"] is True


def test_channel_sessions(client):
    client.post("/api/v1/channels/sessions/wa-155/worker", json={"worker": "w1"}, cookies=_cookies())
    s = client.get("/api/v1/channels/sessions/wa-155", cookies=_cookies()).json()
    assert s["selected_worker"] == "w1"
