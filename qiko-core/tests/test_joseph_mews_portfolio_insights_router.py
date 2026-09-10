import json

from app.core.config import get_settings


def _headers(api_key: str = "test-key") -> dict:
    return {"X-Api-Key": api_key, "X-Tenant-Id": "joseph-mews"}


def _payload(request_id: str = "req-1", **overrides) -> dict:
    payload = {
        "requestId": request_id,
        "properties": [
            {"propertyName": "Marina Heights Unit 12B", "location": "Manchester",
             "postcode": "M1 1AA", "region": "North West", "grossYieldPct": 6.2,
             "status": "tenanted"},
        ],
    }
    payload.update(overrides)
    return payload


def _enable_api_key(monkeypatch, key: str = "test-key"):
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", key)


def test_portfolio_insights_requires_the_api_key(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio", json=_payload(),
        headers={"X-Tenant-Id": "joseph-mews"},
    )
    assert response.status_code == 403


def test_portfolio_insights_rejects_an_unknown_tenant(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.post(
        "/api/v1/tenants/some-other-tenant/insights/portfolio", json=_payload(),
        headers=_headers(),
    )
    assert response.status_code == 404


def test_portfolio_insights_returns_categorized_cards(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": json.dumps({
                "cards": [{
                    "category": "concentration", "headline": "All your properties are in Manchester.",
                    "evidence": "1 of 1 properties are in the North West region.",
                }],
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio", json=_payload("req-ok"), headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == "req-ok"
    assert body["cards"][0]["category"] == "concentration"


def test_portfolio_insights_returns_an_error_shape_on_generation_failure(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": "not json at all"})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio", json=_payload("req-fail"), headers=_headers(),
    )
    assert response.status_code == 200
    assert response.json()["error"]["code"] == "GENERATION_FAILED"


def test_portfolio_insights_returns_empty_cards_without_calling_the_model_for_an_empty_portfolio(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def __init__(self):
            self.called = False

        def generate(self, prompt, **_kwargs):
            self.called = True
            return type("R", (), {"text": json.dumps({"cards": [{"headline": "fabricated", "evidence": "noise"}]})})()

    provider = Provider()
    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: provider)

    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio", json=_payload("req-empty", properties=[]),
        headers=_headers(),
    )
    assert response.status_code == 200
    assert response.json()["cards"] == []
    assert provider.called is False


def test_portfolio_insights_is_idempotent_on_request_id(client, monkeypatch):
    _enable_api_key(monkeypatch)
    call_count = {"n": 0}

    class Provider:
        def generate(self, prompt, **_kwargs):
            call_count["n"] += 1
            return type("R", (), {"text": json.dumps({
                "cards": [{"headline": f"Call number {call_count['n']}.", "evidence": "e"}],
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    first = client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio", json=_payload("req-dup"), headers=_headers(),
    )
    second = client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio", json=_payload("req-dup"), headers=_headers(),
    )
    assert first.json()["cards"] == second.json()["cards"]
    assert call_count["n"] == 1


def test_portfolio_insights_and_property_insight_caches_are_independent(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": json.dumps({
                "summary": "Property summary.", "cards": [{"headline": "Portfolio card.", "evidence": "e"}],
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    property_payload = {
        "requestId": "shared-id",
        "property": {"grossYieldPct": 6.0},
    }
    property_response = client.post(
        "/api/v1/tenants/joseph-mews/insights/property", json=property_payload, headers=_headers(),
    )
    portfolio_response = client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio", json=_payload("shared-id"), headers=_headers(),
    )
    assert property_response.status_code == 200
    assert portfolio_response.status_code == 200
    assert "cards" not in property_response.json()
    assert "summary" not in portfolio_response.json()


def test_outcome_can_be_reported_against_a_portfolio_insight_request_id(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": json.dumps({"cards": []})})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio", json=_payload("req-outcome"), headers=_headers(),
    )
    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/req-outcome/outcome",
        json={"outcome": "accurate"}, headers=_headers(),
    )
    assert response.status_code == 200
    assert response.json()["recorded"] is True
