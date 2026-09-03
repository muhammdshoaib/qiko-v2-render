"""Tests for the backward-data outcome endpoints (3 Sep): consumers report whether a previously
generated signal summary / property insight turned out accurate."""

import json

from app.core.config import get_settings


def _headers(api_key: str = "test-key") -> dict:
    return {"X-Api-Key": api_key, "X-Tenant-Id": "joseph-mews"}


def _enable_api_key(monkeypatch, key: str = "test-key"):
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", key)


def _generate_signal(client, monkeypatch, request_id: str) -> None:
    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": json.dumps({
                "summary": "Jane viewed Marina Heights.", "suggestedNextAction": "Call Jane.",
            })})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())
    client.post(
        "/api/v1/tenants/joseph-mews/signals/summarize",
        json={
            "requestId": request_id,
            "signal": {"id": 1, "signalType": "x", "triggeringActivity": "x", "intentLevel": "low"},
            "investor": {"id": 1},
        },
        headers=_headers(),
    )


def _generate_insight(client, monkeypatch, request_id: str) -> None:
    class Provider:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": json.dumps({"summary": "Strong yield here."})})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())
    client.post(
        "/api/v1/tenants/joseph-mews/insights/property",
        json={"requestId": request_id, "property": {"id": 1, "grossYieldPct": 5.0}},
        headers=_headers(),
    )


def test_reporting_a_signal_outcome_requires_a_known_request_id(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/signals/never-generated/outcome",
        json={"outcome": "accurate"}, headers=_headers(),
    )
    assert response.status_code == 404


def test_reporting_a_signal_outcome_succeeds_for_a_generated_signal(client, monkeypatch):
    _enable_api_key(monkeypatch)
    _generate_signal(client, monkeypatch, "signal-1")

    response = client.post(
        "/api/v1/tenants/joseph-mews/signals/signal-1/outcome",
        json={"outcome": "accurate", "note": "Investor booked a call the same day."},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"requestId": "signal-1", "recorded": True}


def test_reporting_an_insight_outcome_succeeds_for_a_generated_insight(client, monkeypatch):
    _enable_api_key(monkeypatch)
    _generate_insight(client, monkeypatch, "insight-1")

    response = client.post(
        "/api/v1/tenants/joseph-mews/insights/insight-1/outcome",
        json={"outcome": "inaccurate"}, headers=_headers(),
    )

    assert response.status_code == 200


def test_outcome_report_rejects_an_unknown_outcome_value(client, monkeypatch):
    _enable_api_key(monkeypatch)
    _generate_signal(client, monkeypatch, "signal-2")

    response = client.post(
        "/api/v1/tenants/joseph-mews/signals/signal-2/outcome",
        json={"outcome": "sort-of"}, headers=_headers(),
    )

    assert response.status_code == 422


def test_outcome_report_requires_the_api_key(client, monkeypatch):
    _enable_api_key(monkeypatch)
    _generate_signal(client, monkeypatch, "signal-3")

    response = client.post(
        "/api/v1/tenants/joseph-mews/signals/signal-3/outcome",
        json={"outcome": "accurate"}, headers={"X-Tenant-Id": "joseph-mews"},
    )

    assert response.status_code == 403


def test_outcomes_summary_counts_by_kind_and_value(client, monkeypatch):
    _enable_api_key(monkeypatch)
    _generate_signal(client, monkeypatch, "signal-summary-1")
    _generate_signal(client, monkeypatch, "signal-summary-2")
    _generate_insight(client, monkeypatch, "insight-summary-1")
    client.post("/api/v1/tenants/joseph-mews/signals/signal-summary-1/outcome",
               json={"outcome": "accurate"}, headers=_headers())
    client.post("/api/v1/tenants/joseph-mews/signals/signal-summary-2/outcome",
               json={"outcome": "inaccurate"}, headers=_headers())
    client.post("/api/v1/tenants/joseph-mews/insights/insight-summary-1/outcome",
               json={"outcome": "accurate"}, headers=_headers())

    response = client.get("/api/v1/tenants/joseph-mews/outcomes/summary", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["signals"]["accurate"] >= 1
    assert body["signals"]["inaccurate"] >= 1
    assert body["insights"]["accurate"] >= 1


def test_reporting_the_same_request_id_twice_overwrites_rather_than_double_counts(client, monkeypatch):
    _enable_api_key(monkeypatch)
    _generate_signal(client, monkeypatch, "signal-overwrite")

    client.post("/api/v1/tenants/joseph-mews/signals/signal-overwrite/outcome",
               json={"outcome": "inaccurate"}, headers=_headers())
    client.post("/api/v1/tenants/joseph-mews/signals/signal-overwrite/outcome",
               json={"outcome": "accurate"}, headers=_headers())

    from app.modules.joseph_mews.router import _signal_outcomes
    assert _signal_outcomes._by_request["signal-overwrite"].outcome == "accurate"
