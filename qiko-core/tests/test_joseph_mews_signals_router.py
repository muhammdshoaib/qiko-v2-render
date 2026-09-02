import json

from app.core.config import get_settings


def _headers(api_key: str = "test-key") -> dict:
    return {"X-Api-Key": api_key, "X-Tenant-Id": "joseph-mews"}


def _payload(request_id: str = "req-1") -> dict:
    return {
        "requestId": request_id,
        "signal": {
            "id": 123, "signalType": "property_revisit",
            "triggeringActivity": "Viewed Property Detail 3x in 24h", "intentLevel": "high",
        },
        "investor": {"id": 45, "firstName": "Jane"},
        "property": {"id": 88, "name": "Marina Heights Unit 12B"},
    }


def _enable_api_key(monkeypatch, key: str = "test-key"):
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", key)


def test_summarize_requires_the_api_key(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/signals/summarize", json=_payload(),
        headers={"X-Tenant-Id": "joseph-mews"},
    )
    assert response.status_code == 403


def test_summarize_rejects_the_wrong_api_key(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/signals/summarize", json=_payload(),
        headers=_headers("wrong-key"),
    )
    assert response.status_code == 403


def test_summarize_rejects_an_unknown_tenant(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.post(
        "/api/v1/tenants/some-other-tenant/signals/summarize", json=_payload(),
        headers=_headers(),
    )
    assert response.status_code == 404


def test_summarize_returns_a_grounded_summary(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": json.dumps({
                "summary": "Jane viewed Marina Heights three times.",
                "suggestedNextAction": "Call Jane.",
                "groundedIn": ["signal.triggeringActivity"],
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    response = client.post(
        "/api/v1/tenants/joseph-mews/signals/summarize", json=_payload("req-ok"), headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == "req-ok"
    assert body["summary"] == "Jane viewed Marina Heights three times."
    assert body["suggestedNextAction"] == "Call Jane."
    assert "error" not in body


def test_summarize_returns_an_error_shape_on_generation_failure(client, monkeypatch):
    _enable_api_key(monkeypatch)

    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": "not json at all"})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    response = client.post(
        "/api/v1/tenants/joseph-mews/signals/summarize", json=_payload("req-fail"), headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == "req-fail"
    assert body["error"]["code"] == "GENERATION_FAILED"


def test_summarize_is_idempotent_on_request_id(client, monkeypatch):
    _enable_api_key(monkeypatch)
    call_count = {"n": 0}

    class Provider:
        def generate(self, prompt, **_kwargs):
            call_count["n"] += 1
            return type("R", (), {"text": json.dumps({
                "summary": f"Call number {call_count['n']}.", "suggestedNextAction": "Follow up.",
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())

    first = client.post(
        "/api/v1/tenants/joseph-mews/signals/summarize", json=_payload("req-dup"), headers=_headers(),
    )
    second = client.post(
        "/api/v1/tenants/joseph-mews/signals/summarize", json=_payload("req-dup"), headers=_headers(),
    )
    assert first.json()["summary"] == second.json()["summary"]
    assert call_count["n"] == 1
