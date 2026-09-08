import json

from app.core.config import get_settings
from app.modules.joseph_mews.investor_token import create_investor_activity_token


def _enable_investor_secret(monkeypatch, secret: str = "test-investor-secret"):
    monkeypatch.setattr(get_settings(), "investor_activity_token_secret", secret)
    return secret


def _investor_headers(monkeypatch, *, tenant="joseph-mews", investor_ref="inv-1"):
    secret = _enable_investor_secret(monkeypatch)
    token = create_investor_activity_token(tenant=tenant, investor_ref=investor_ref, secret=secret)
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(monkeypatch, api_key: str = "test-key") -> dict:
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", api_key)
    return {"X-Api-Key": api_key, "X-Tenant-Id": "joseph-mews"}


def test_post_activity_requires_a_bearer_token(client):
    response = client.post(
        "/api/v1/tenants/joseph-mews/activity",
        json={"category": "screen", "label": "Dashboard"},
    )
    assert response.status_code == 401


def test_post_activity_rejects_a_token_for_a_different_tenant(client, monkeypatch):
    headers = _investor_headers(monkeypatch, tenant="some-other-tenant")
    response = client.post(
        "/api/v1/tenants/joseph-mews/activity",
        json={"category": "screen", "label": "Dashboard"}, headers=headers,
    )
    assert response.status_code == 403


def test_post_activity_records_a_screen_visit(client, monkeypatch):
    headers = _investor_headers(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/activity",
        json={"category": "screen", "label": "Dashboard"}, headers=headers,
    )
    assert response.status_code == 201


def test_post_activity_rejects_an_unexpected_property_id_field(client, monkeypatch):
    headers = _investor_headers(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/activity",
        json={"category": "property_visit", "label": "PropertyDetail", "propertyId": 88},
        headers=headers,
    )
    assert response.status_code == 422


def test_get_activity_requires_the_api_key(client, monkeypatch):
    _admin_headers(monkeypatch)
    response = client.get(
        "/api/v1/tenants/joseph-mews/activity", params={"investorRef": "inv-1"},
        headers={"X-Tenant-Id": "joseph-mews"},
    )
    assert response.status_code == 403


def test_get_activity_returns_recorded_events_for_that_investor(client, monkeypatch):
    investor_headers = _investor_headers(monkeypatch)
    client.post(
        "/api/v1/tenants/joseph-mews/activity",
        json={
            "category": "property_visit", "label": "PropertyDetail",
            "propertyName": "The Mayfair Residence", "location": "Mount Street, Mayfair",
            "postcode": "W1K 2HQ",
        },
        headers=investor_headers,
    )
    admin_headers = _admin_headers(monkeypatch)
    response = client.get(
        "/api/v1/tenants/joseph-mews/activity", params={"investorRef": "inv-1"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["investorRef"] == "inv-1"
    assert body["events"][0]["propertyName"] == "The Mayfair Residence"
    assert "propertyId" not in json.dumps(body)


def test_intent_signals_requires_the_api_key(client, monkeypatch):
    _admin_headers(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/activity/intent-signals",
        json={"requestId": "r1", "investorRef": "inv-1"},
        headers={"X-Tenant-Id": "joseph-mews"},
    )
    assert response.status_code == 403


def test_intent_signals_generates_from_stored_activity(client, monkeypatch):
    investor_headers = _investor_headers(monkeypatch)
    for _ in range(5):
        client.post(
            "/api/v1/tenants/joseph-mews/activity",
            json={
                "category": "property_visit", "label": "PropertyDetail",
                "propertyName": "Marina Heights", "location": "Manchester", "postcode": "M1 1AA",
            },
            headers=investor_headers,
        )

    class Provider:
        def generate(self, prompt, **_kwargs):
            assert "Manchester" in prompt
            return type("R", (), {"text": json.dumps({
                "signals": [{"signal": "Interested in Manchester property", "strength": "high",
                            "evidence": "Manchester-area property viewed 5x"}],
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    admin_headers = _admin_headers(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/activity/intent-signals",
        json={"requestId": "r1", "investorRef": "inv-1"}, headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == "r1"
    assert body["signals"][0]["signal"] == "Interested in Manchester property"


def test_intent_signals_returns_an_error_shape_on_generation_failure(client, monkeypatch):
    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": "not json at all"})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    admin_headers = _admin_headers(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/activity/intent-signals",
        json={"requestId": "r1", "investorRef": "inv-1"}, headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == "GENERATION_FAILED"
