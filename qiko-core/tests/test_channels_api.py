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


def test_outbound_sends(client):
    assert client.post(
        "/api/v1/channels/whatsapp/send",
        json={"to": "155", "text": "hi", "worker_id": "w1"},
        cookies=_cookies()).json()["stub"] is True
    assert client.post(
        "/api/v1/channels/gmail/send",
        json={"to": "a@invalid", "subject": "S", "body": "B", "worker_id": "w1"},
        cookies=_cookies()).json()["sent"] is True
    assert client.post(
        "/api/v1/channels/clickup/task",
        json={"list_id": "L", "name": "N", "worker_id": "w1"},
        cookies=_cookies()).json()["id"]


def test_outbound_requires_editor(client):
    assert client.post("/api/v1/channels/whatsapp/send", json={"to": "1", "text": "x", "worker_id": "w1"}, cookies=auth_cookies("chan", "viewer")).status_code == 403


def test_calendly(client):
    assert len(client.get("/api/v1/channels/calendly/slots", params={"event_type": "intro", "worker_id": "w1"}, cookies=_cookies()).json()["slots"]) == 2
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
