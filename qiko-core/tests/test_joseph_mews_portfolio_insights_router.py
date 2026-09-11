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


# --- GET read-back, 1 to 3 insights, investor + wider JM portfolio (JM2-1133) -----------------

def _generated_cards(monkeypatch, cards: list[dict]):
    class Provider:
        prompts: list[str] = []

        def generate(self, prompt, **_kwargs):
            Provider.prompts.append(prompt)
            return type("R", (), {"text": json.dumps({"cards": cards})})()

    import app.modules.joseph_mews.router as router_module
    monkeypatch.setattr(router_module, "get_provider", lambda: Provider())
    return Provider


def test_get_portfolio_insights_reads_back_what_was_generated(client, monkeypatch):
    """The client's Property Insights requirement is a GET: the app and the admin panel both
    display these on load, and only a POST existed."""
    _enable_api_key(monkeypatch)
    _generated_cards(monkeypatch, [{
        "category": "concentration", "headline": "All your properties are in Manchester.",
        "evidence": "1 of 1 properties are in the North West region.",
    }])
    client.post("/api/v1/tenants/joseph-mews/insights/portfolio",
                json=_payload("req-read", investor={"id": 45}), headers=_headers())

    response = client.get("/api/v1/tenants/joseph-mews/insights/portfolio",
                          params={"investorRef": "45"}, headers=_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["investorRef"] == "45"
    assert body["cards"][0]["headline"] == "All your properties are in Manchester."


def test_get_portfolio_insights_404s_when_nothing_has_been_generated(client, monkeypatch):
    """404 rather than an empty list, so the caller can tell 'not generated yet' from 'generated
    and nothing was grounded enough to say'."""
    _enable_api_key(monkeypatch)
    response = client.get("/api/v1/tenants/joseph-mews/insights/portfolio",
                          params={"investorRef": "nobody"}, headers=_headers())
    assert response.status_code == 404


def test_get_portfolio_insights_returns_at_most_three(client, monkeypatch):
    """"a max of 3 insights ... and a minimum of 1". A model that returns five must not quietly
    reshape the overview screen."""
    _enable_api_key(monkeypatch)
    _generated_cards(monkeypatch, [
        {"category": "concentration", "headline": f"Card {i}", "evidence": "e"} for i in range(5)
    ])
    client.post("/api/v1/tenants/joseph-mews/insights/portfolio",
                json=_payload("req-cap", investor={"id": 45}), headers=_headers())

    response = client.get("/api/v1/tenants/joseph-mews/insights/portfolio",
                          params={"investorRef": "45"}, headers=_headers())
    assert len(response.json()["cards"]) == 3


def test_platform_averages_reach_the_model_for_the_wider_portfolio_comparison(client, monkeypatch):
    """The requirement names two scopes: the investor's own portfolio AND "the wider portfolio
    across the JM investors". The second is only groundable if the caller's platform-wide
    aggregates actually reach the prompt."""
    _enable_api_key(monkeypatch)
    Provider = _generated_cards(monkeypatch, [
        {"category": "regional_performance", "headline": "London is up 10% across JM investors.",
         "evidence": "platformAverages.london.growthPct3m = 10"}])
    client.post(
        "/api/v1/tenants/joseph-mews/insights/portfolio",
        json=_payload("req-platform", investor={"id": 45},
                      platformAverages={"london": {"growthPct3m": 10}}),
        headers=_headers(),
    )
    assert "platformAverages" in Provider.prompts[0]
    assert "growthPct3m" in Provider.prompts[0]


def test_get_portfolio_insights_is_tenant_scoped(client, monkeypatch):
    _enable_api_key(monkeypatch)
    response = client.get("/api/v1/tenants/some-other-tenant/insights/portfolio",
                          params={"investorRef": "45"},
                          headers={"X-Api-Key": "test-key", "X-Tenant-Id": "some-other-tenant"})
    assert response.status_code == 404
