from tests.helpers import auth_cookies

C = auth_cookies("chan", "owner")


def test_outbound_sends(client):
    assert client.post("/api/v1/channels/whatsapp/send", json={"to": "155", "text": "hi"}, cookies=C).json()["stub"] is True
    assert client.post("/api/v1/channels/gmail/send", json={"to": "a@x.com", "subject": "S", "body": "B"}, cookies=C).json()["sent"] is True
    assert client.post("/api/v1/channels/slack/send", json={"channel": "#g", "text": "hi"}, cookies=C).json()["ok"] is True
    assert client.post("/api/v1/channels/clickup/task", json={"list_id": "L", "name": "N"}, cookies=C).json()["id"]


def test_outbound_requires_editor(client):
    assert client.post("/api/v1/channels/whatsapp/send", json={"to": "1", "text": "x"}, cookies=auth_cookies("chan", "viewer")).status_code == 403


def test_calendly(client):
    assert len(client.get("/api/v1/channels/calendly/slots", params={"event_type": "intro"}, cookies=C).json()["slots"]) == 2
    booked = client.post("/api/v1/channels/calendly/book",
                         json={"event_type": "intro", "invitee_email": "a@x.com", "start": "2026-07-10T09:00:00Z"}, cookies=C).json()
    assert booked["booked"] is True


def test_slack_install_and_link(client):
    assert "slack.com/oauth" in client.get("/api/v1/channels/slack/install", params={"state": "s1"}, cookies=C).json()["url"]
    assert client.post("/api/v1/channels/slack/link",
                       json={"team_id": "T1", "slack_user_id": "U1", "worker_id": "w1"}, cookies=C).json()["linked"] is True


def test_channel_sessions(client):
    client.post("/api/v1/channels/sessions/wa-155/worker", json={"worker": "w1"}, cookies=C)
    s = client.get("/api/v1/channels/sessions/wa-155", cookies=C).json()
    assert s["selected_worker"] == "w1"
