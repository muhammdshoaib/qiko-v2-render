import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.email.sender import ConsoleEmailSender, get_email_sender


def test_labs_contact_sends_email(client):
    resp = client.post("/api/v1/marketing/labs-contact", json={
        "name": "Jane Doe",
        "work_email": "jane@example.com",
        "company": "Acme Corp",
        "company_size": "51 - 250",
        "build_request": "A workflow agent for support triage.",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "message" in body


def test_labs_contact_requires_valid_email(client):
    resp = client.post("/api/v1/marketing/labs-contact", json={
        "name": "Jane Doe",
        "work_email": "not-an-email",
        "company": "Acme Corp",
        "company_size": "51 - 250",
        "build_request": "A workflow agent for support triage.",
    })
    assert resp.status_code == 422


def test_labs_contact_requires_all_fields(client):
    resp = client.post("/api/v1/marketing/labs-contact", json={"name": "Jane Doe"})
    assert resp.status_code == 422


# --- WEB-1030: public /api/v1/contact endpoint ---


@pytest.fixture
def contact_client():
    app = create_app()
    mail = ConsoleEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: mail
    yield TestClient(app), mail
    app.dependency_overrides.clear()


def _payload(**overrides):
    body = {
        "topic": "general",
        "name": "Jane Doe",
        "email": "jane@example.com",
        "message": "I would like to know more about Qiko.",
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize("topic", ["general", "labs", "signal"])
def test_contact_sends_one_email_per_topic(contact_client, topic):
    client, mail = contact_client
    resp = client.post("/api/v1/contact", json=_payload(topic=topic))
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent"}
    assert len(mail.sent) == 1
    sent = mail.sent[0]
    assert sent["to"] == "contact@qiko.ai"
    assert topic in sent["body"] or topic in sent["subject"]


def test_contact_body_carries_reply_details(contact_client):
    client, mail = contact_client
    resp = client.post("/api/v1/contact", json=_payload())
    assert resp.status_code == 200
    sent = mail.sent[0]
    assert "Jane Doe" in sent["body"]
    assert "jane@example.com" in sent["body"]
    assert "I would like to know more about Qiko." in sent["body"]


@pytest.mark.parametrize("overrides", [
    {"topic": "sales"},
    {"topic": "GENERAL"},
    {"message": "x" * 4001},
    {"message": ""},
    {"name": ""},
    {"email": "not-an-email"},
    {"email": "a" * 250 + "@x.com"},
])
def test_contact_rejects_invalid_input_with_400(contact_client, overrides):
    client, mail = contact_client
    resp = client.post("/api/v1/contact", json=_payload(**overrides))
    assert resp.status_code == 400
    assert mail.sent == []


def test_contact_missing_field_is_400(contact_client):
    client, mail = contact_client
    resp = client.post("/api/v1/contact", json={"topic": "general", "name": "Jane Doe"})
    assert resp.status_code == 400
    assert mail.sent == []


def test_contact_returns_502_when_sender_rejects():
    app = create_app()

    class RejectingSender:
        def send(self, *, to, subject, body, html=None):
            return False

    app.dependency_overrides[get_email_sender] = RejectingSender
    resp = TestClient(app).post("/api/v1/contact", json=_payload())
    assert resp.status_code == 502
    assert "sent" not in resp.json().get("status", "")


def test_contact_needs_no_authentication(contact_client):
    client, mail = contact_client
    resp = client.post("/api/v1/contact", json=_payload())
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


def test_contact_does_not_log_message_body(contact_client, caplog):
    client, mail = contact_client
    secret = "confidential launch plans xyzzy"
    with caplog.at_level(logging.INFO):
        resp = client.post("/api/v1/contact", json=_payload(message=secret))
    assert resp.status_code == 200
    assert secret not in caplog.text
    assert "jane@example.com" not in caplog.text
