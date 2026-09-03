import json

from app.core.config import get_settings


def _headers(api_key: str = "test-key") -> dict:
    return {"X-Api-Key": api_key, "X-Tenant-Id": "joseph-mews"}


def _payload(request_id: str = "req-1") -> dict:
    return {
        "requestId": request_id,
        "investor": {"id": 45, "firstName": "Jane"},
        "property": {"id": 88, "name": "Marina Heights Unit 12B", "grossYieldPct": 6.2},
        "portfolioAverages": {"grossYieldPct": 5.4},
    }


def _enable_api_key(monkeypatch, key: str = "test-key"):
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", key)


def test_insight_requires_the_api_key(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/property", json=_payload(),
        headers={"X-Tenant-Id": "joseph-mews"},
    )
    assert response.status_code == 403


def test_insight_rejects_an_unknown_tenant(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.post(
        "/api/v1/tenants/some-other-tenant/insights/property", json=_payload(),
        headers=_headers(),
    )
    assert response.status_code == 404


def test_insight_returns_a_grounded_summary_with_no_suggested_action(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": json.dumps({
                "summary": "This property's yield is 0.8pp ahead of your portfolio average.",
                "groundedIn": ["property.grossYieldPct"],
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/property", json=_payload("req-ok"), headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == "req-ok"
    assert body["summary"] == "This property's yield is 0.8pp ahead of your portfolio average."
    assert "suggestedNextAction" not in body
    assert "error" not in body


def test_insight_returns_an_error_shape_on_generation_failure(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": "not json at all"})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/property", json=_payload("req-fail"), headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == "req-fail"
    assert body["error"]["code"] == "GENERATION_FAILED"


def test_insight_is_idempotent_on_request_id(client, monkeypatch):
    _enable_api_key(monkeypatch)
    call_count = {"n": 0}

    class Provider:
        def generate(self, prompt, **_kwargs):
            call_count["n"] += 1
            return type("R", (), {"text": json.dumps({"summary": f"Call number {call_count['n']}."})})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    first = client.post(
        "/api/v1/tenants/joseph-mews/insights/property", json=_payload("req-dup"), headers=_headers(),
    )
    second = client.post(
        "/api/v1/tenants/joseph-mews/insights/property", json=_payload("req-dup"), headers=_headers(),
    )
    assert first.json()["summary"] == second.json()["summary"]
    assert call_count["n"] == 1


def test_insight_and_signal_caches_are_independent_for_the_same_request_id(client, monkeypatch):
    # Both endpoints share the _ResultCache class but must use separate instances - otherwise a
    # signal-summarize call and a property-insight call with the same requestId would collide.
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": json.dumps({
                "summary": "Insight summary.", "suggestedNextAction": "Signal action.",
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    signal_payload = {
        "requestId": "shared-id",
        "signal": {"id": 1, "signalType": "x", "triggeringActivity": "x", "intentLevel": "low"},
        "investor": {"id": 1},
    }
    signal_response = client.post(
        "/api/v1/tenants/joseph-mews/signals/summarize", json=signal_payload, headers=_headers(),
    )
    insight_response = client.post(
        "/api/v1/tenants/joseph-mews/insights/property", json=_payload("shared-id"), headers=_headers(),
    )
    assert signal_response.status_code == 200
    assert insight_response.status_code == 200
    assert "suggestedNextAction" not in insight_response.json()
