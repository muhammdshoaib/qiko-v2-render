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
    # Needs to clear the deterministic signal-eligibility guardrail first, or the model is never
    # called at all and the response is an empty signals list rather than a generation failure.
    investor_headers = _investor_headers(monkeypatch)
    for _ in range(3):
        client.post(
            "/api/v1/tenants/joseph-mews/activity",
            json={"category": "property_visit", "label": "PropertyDetail",
                 "propertyName": "Marina Heights", "location": "Manchester", "postcode": "M1 1AA"},
            headers=investor_headers,
        )

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


def test_intent_signals_returns_empty_signals_without_calling_the_llm_when_activity_is_sparse(client, monkeypatch):
    investor_headers = _investor_headers(monkeypatch)
    client.post(
        "/api/v1/tenants/joseph-mews/activity",
        json={"category": "screen", "label": "Dashboard"}, headers=investor_headers,
    )

    class Provider:
        def __init__(self):
            self.called = False

        def generate(self, prompt, **_kwargs):
            self.called = True
            return type("R", (), {"text": '{"signals": [{"signal": "fabricated", "strength": "high", "evidence": "noise"}]}'})()

    provider = Provider()
    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: provider)

    admin_headers = _admin_headers(monkeypatch)
    response = client.post(
        "/api/v1/tenants/joseph-mews/activity/intent-signals",
        json={"requestId": "r1", "investorRef": "inv-1"}, headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["signals"] == []


# --- Admin feed: activity across all investors, searchable/filterable/sortable (JM2-1133) -----

def _record(client, monkeypatch, investor_ref: str, **event):
    headers = _investor_headers(monkeypatch, investor_ref=investor_ref)
    response = client.post("/api/v1/tenants/joseph-mews/activity", json=event, headers=headers)
    assert response.status_code == 201


def _signal_provider(monkeypatch, signals: list[dict]):
    class Provider:
        calls = 0

        def generate(self, prompt, **_kwargs):
            Provider.calls += 1
            return type("R", (), {"text": json.dumps({"signals": signals})})()

    import app.modules.joseph_mews.router as router_module
    provider = Provider()
    monkeypatch.setattr(router_module, "get_provider", lambda: provider)
    return Provider


def test_get_activity_without_an_investor_ref_returns_every_investor(client, monkeypatch):
    """The client's third requirement: one feed across the whole platform, not per investor."""
    _record(client, monkeypatch, "inv-a", category="screen", label="Dashboard")
    _record(client, monkeypatch, "inv-b", category="screen", label="Explore")

    response = client.get("/api/v1/tenants/joseph-mews/activity",
                          headers=_admin_headers(monkeypatch))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {e["investorRef"] for e in body["events"]} == {"inv-a", "inv-b"}


def test_get_activity_searches_filters_and_sorts(client, monkeypatch):
    _record(client, monkeypatch, "inv-a", category="screen", label="Dashboard")
    _record(client, monkeypatch, "inv-a", category="property_visit", label="PropertyDetail",
            propertyName="Marina Heights", location="Manchester", postcode="M1 1AA")
    _record(client, monkeypatch, "inv-b", category="calculator_step", label="YieldStep")
    headers = _admin_headers(monkeypatch)

    searched = client.get("/api/v1/tenants/joseph-mews/activity",
                          params={"q": "manchester"}, headers=headers).json()
    assert searched["total"] == 1
    assert searched["events"][0]["location"] == "Manchester"

    filtered = client.get("/api/v1/tenants/joseph-mews/activity",
                          params={"category": "screen"}, headers=headers).json()
    assert filtered["total"] == 1 and filtered["events"][0]["label"] == "Dashboard"

    ascending = client.get("/api/v1/tenants/joseph-mews/activity",
                           params={"sort": "occurredAt"}, headers=headers).json()
    descending = client.get("/api/v1/tenants/joseph-mews/activity",
                            params={"sort": "-occurredAt"}, headers=headers).json()
    assert [e["label"] for e in ascending["events"]] == \
        list(reversed([e["label"] for e in descending["events"]]))


def test_get_activity_paginates_with_a_total_the_page_alone_cannot_give(client, monkeypatch):
    for index in range(5):
        _record(client, monkeypatch, "inv-a", category="screen", label=f"Screen{index}")
    headers = _admin_headers(monkeypatch)

    page = client.get("/api/v1/tenants/joseph-mews/activity",
                      params={"limit": 2, "offset": 0}, headers=headers).json()
    assert len(page["events"]) == 2 and page["total"] == 5
    second = client.get("/api/v1/tenants/joseph-mews/activity",
                        params={"limit": 2, "offset": 2}, headers=headers).json()
    assert {e["label"] for e in page["events"]}.isdisjoint({e["label"] for e in second["events"]})


def test_get_activity_rejects_an_unknown_sort_instead_of_silently_reordering(client, monkeypatch):
    response = client.get("/api/v1/tenants/joseph-mews/activity",
                          params={"sort": "label; DROP TABLE"}, headers=_admin_headers(monkeypatch))
    assert response.status_code == 422
    assert "unsupported sort" in response.json()["detail"]


def test_get_activity_is_tenant_scoped(client, monkeypatch):
    """Another tenant cannot read this feed at all: require_worker_caller rejects a tenant with
    no Joseph Mews worker before the store is ever queried, so the isolation is an authorisation
    failure rather than an empty result."""
    _record(client, monkeypatch, "inv-a", category="screen", label="Dashboard")
    monkeypatch.setattr(get_settings(), "jm_backend_api_key", "test-key")
    response = client.get("/api/v1/tenants/other-tenant/activity",
                          headers={"X-Api-Key": "test-key", "X-Tenant-Id": "other-tenant"})
    assert response.status_code == 404


# --- Admin feed: intent signals (JM2-1133) ----------------------------------------------------

def test_get_signals_lists_every_investors_signals_after_generation(client, monkeypatch):
    """The client's fourth requirement: all available intent signals for all investors."""
    for ref in ("inv-a", "inv-b"):
        for _ in range(3):
            _record(client, monkeypatch, ref, category="property_visit", label="PropertyDetail",
                    propertyName="Marina Heights", location="Manchester", postcode="M1 1AA")
    _signal_provider(monkeypatch, [
        {"signal": "Interested in Manchester", "strength": "high", "evidence": "viewed 3x"}])
    headers = _admin_headers(monkeypatch)
    for ref in ("inv-a", "inv-b"):
        client.post("/api/v1/tenants/joseph-mews/activity/intent-signals",
                    json={"requestId": f"r-{ref}", "investorRef": ref}, headers=headers)

    response = client.get("/api/v1/tenants/joseph-mews/signals", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {s["investorRef"] for s in body["signals"]} == {"inv-a", "inv-b"}
    assert body["signals"][0]["strength"] == "high"


def test_get_signals_reads_stored_rows_without_calling_the_model_again(client, monkeypatch):
    for _ in range(3):
        _record(client, monkeypatch, "inv-a", category="property_visit", label="PropertyDetail",
                propertyName="Marina Heights", location="Manchester", postcode="M1 1AA")
    Provider = _signal_provider(monkeypatch, [
        {"signal": "Interested in Manchester", "strength": "high", "evidence": "viewed 3x"}])
    headers = _admin_headers(monkeypatch)
    client.post("/api/v1/tenants/joseph-mews/activity/intent-signals",
                json={"requestId": "r1", "investorRef": "inv-a"}, headers=headers)
    calls_after_generation = Provider.calls

    for _ in range(3):
        client.get("/api/v1/tenants/joseph-mews/signals", headers=headers)
        client.get("/api/v1/tenants/joseph-mews/signals",
                   params={"investorRef": "inv-a"}, headers=headers)
    assert Provider.calls == calls_after_generation


def test_get_signals_for_one_investor_says_so_when_activity_is_too_sparse(client, monkeypatch):
    """The client's fifth requirement: 'If not enough activities to generate any intent signals,
    a clear response in that case.' An empty list alone cannot say that."""
    _record(client, monkeypatch, "inv-a", category="screen", label="Dashboard")
    Provider = _signal_provider(monkeypatch, [{"signal": "x", "strength": "high", "evidence": "y"}])

    response = client.get("/api/v1/tenants/joseph-mews/signals",
                          params={"investorRef": "inv-a"}, headers=_admin_headers(monkeypatch))
    assert response.status_code == 200
    body = response.json()
    assert body["signals"] == [] and body["insufficientActivity"] is True
    assert "at least" in body["reason"] and body["activityEventCount"] == 1
    assert Provider.calls == 0  # never pays for a generation it already knows cannot be grounded


def test_get_signals_for_one_investor_drafts_once_when_never_processed(client, monkeypatch):
    """An investor with enough activity but no stored signals must not show as blank just
    because nobody POSTed a generation for them yet."""
    for _ in range(3):
        _record(client, monkeypatch, "inv-a", category="property_visit", label="PropertyDetail",
                propertyName="Marina Heights", location="Manchester", postcode="M1 1AA")
    Provider = _signal_provider(monkeypatch, [
        {"signal": "Interested in Manchester", "strength": "high", "evidence": "viewed 3x"}])
    headers = _admin_headers(monkeypatch)

    first = client.get("/api/v1/tenants/joseph-mews/signals",
                       params={"investorRef": "inv-a"}, headers=headers).json()
    assert first["signals"][0]["signal"] == "Interested in Manchester"
    assert first["insufficientActivity"] is False
    assert Provider.calls == 1

    client.get("/api/v1/tenants/joseph-mews/signals",
               params={"investorRef": "inv-a"}, headers=headers)
    assert Provider.calls == 1  # second read is served from storage


def test_get_signals_filters_by_strength_and_text(client, monkeypatch):
    for _ in range(3):
        _record(client, monkeypatch, "inv-a", category="property_visit", label="PropertyDetail",
                propertyName="Marina Heights", location="Manchester", postcode="M1 1AA")
    _signal_provider(monkeypatch, [
        {"signal": "Interested in Manchester", "strength": "high", "evidence": "viewed 3x"},
        {"signal": "Browsing documents", "strength": "low", "evidence": "opened 2 docs"},
    ])
    headers = _admin_headers(monkeypatch)
    client.post("/api/v1/tenants/joseph-mews/activity/intent-signals",
                json={"requestId": "r1", "investorRef": "inv-a"}, headers=headers)

    high = client.get("/api/v1/tenants/joseph-mews/signals",
                      params={"strength": "high"}, headers=headers).json()
    assert high["total"] == 1 and high["signals"][0]["strength"] == "high"

    searched = client.get("/api/v1/tenants/joseph-mews/signals",
                          params={"q": "documents"}, headers=headers).json()
    assert searched["total"] == 1 and searched["signals"][0]["signal"] == "Browsing documents"


def test_regenerating_signals_replaces_rather_than_appends(client, monkeypatch):
    """A signal is a current read of behaviour: appending would list one investor twice with
    contradictory strengths."""
    for _ in range(3):
        _record(client, monkeypatch, "inv-a", category="property_visit", label="PropertyDetail",
                propertyName="Marina Heights", location="Manchester", postcode="M1 1AA")
    headers = _admin_headers(monkeypatch)
    _signal_provider(monkeypatch, [{"signal": "First read", "strength": "low", "evidence": "e"}])
    client.post("/api/v1/tenants/joseph-mews/activity/intent-signals",
                json={"requestId": "r1", "investorRef": "inv-a"}, headers=headers)
    _signal_provider(monkeypatch, [{"signal": "Second read", "strength": "high", "evidence": "e"}])
    client.post("/api/v1/tenants/joseph-mews/activity/intent-signals",
                json={"requestId": "r2", "investorRef": "inv-a"}, headers=headers)

    body = client.get("/api/v1/tenants/joseph-mews/signals",
                      params={"investorRef": "inv-a"}, headers=headers).json()
    assert [s["signal"] for s in body["signals"]] == ["Second read"]


def test_a_failed_regeneration_leaves_the_previous_signals_alone(client, monkeypatch):
    for _ in range(3):
        _record(client, monkeypatch, "inv-a", category="property_visit", label="PropertyDetail",
                propertyName="Marina Heights", location="Manchester", postcode="M1 1AA")
    headers = _admin_headers(monkeypatch)
    _signal_provider(monkeypatch, [{"signal": "Good read", "strength": "high", "evidence": "e"}])
    client.post("/api/v1/tenants/joseph-mews/activity/intent-signals",
                json={"requestId": "r1", "investorRef": "inv-a"}, headers=headers)

    class Broken:
        def generate(self, prompt, **_kwargs):
            return type("R", (), {"text": "not json at all"})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Broken())
    client.post("/api/v1/tenants/joseph-mews/activity/intent-signals",
                json={"requestId": "r2", "investorRef": "inv-a"}, headers=headers)

    body = client.get("/api/v1/tenants/joseph-mews/signals",
                      params={"investorRef": "inv-a"}, headers=headers).json()
    assert [s["signal"] for s in body["signals"]] == ["Good read"]


def test_get_signals_requires_the_api_key(client, monkeypatch):
    _admin_headers(monkeypatch)
    response = client.get("/api/v1/tenants/joseph-mews/signals",
                          headers={"X-Tenant-Id": "joseph-mews"})
    assert response.status_code == 403
