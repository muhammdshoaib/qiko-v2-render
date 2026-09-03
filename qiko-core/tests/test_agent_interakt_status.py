"""Tests for GET /agents/{agent_id}/interakt-status -- read-only, reports on the existing
global Interakt/WhatsApp env config rather than introducing a second place to store it."""

from app.core.config import get_settings
from tests.helpers import auth_cookies


def test_reports_not_configured_by_default(client):
    c = auth_cookies("interaktco", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()

    response = client.get(f"/api/v1/agents/{agent['id']}/interakt-status", cookies=c)

    assert response.status_code == 200
    assert response.json() == {"configured": False, "phone_number_configured": False}


def test_reports_configured_when_the_global_settings_are_set(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "interakt_api_key", "test-interakt-key")
    monkeypatch.setattr(settings, "interakt_webhook_secret", "test-webhook-secret")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "1234567890")
    c = auth_cookies("interaktco2", "owner")
    agent = client.post("/api/v1/agents", json={"name": "Joseph Mews"}, cookies=c).json()

    response = client.get(f"/api/v1/agents/{agent['id']}/interakt-status", cookies=c)

    assert response.json() == {"configured": True, "phone_number_configured": True}


def test_404s_for_a_missing_agent(client):
    c = auth_cookies("interaktco3", "owner")
    response = client.get("/api/v1/agents/does-not-exist/interakt-status", cookies=c)
    assert response.status_code == 404
