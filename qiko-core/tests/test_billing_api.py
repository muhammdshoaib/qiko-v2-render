from tests.helpers import auth_cookies

C = auth_cookies("bill", "owner")


def test_checkout_and_portal(client):
    assert "url" in client.post("/api/v1/billing/checkout", json={"customer_id": "cus1", "plan": "pro"}, cookies=C).json()
    assert "url" in client.get("/api/v1/billing/portal/cus1", cookies=C).json()


def test_plans_match_the_real_product(client):
    """Regression: the catalog used to be Free/Pro/Enterprise with a generic worker-count feature
    list. The real product (verified live on stage-app.qiko.ai/app/pricing) is Premium ($49/mo,
    3 workers) and Enterprise (custom pricing, everything in Premium plus more)."""
    plans = client.get("/api/v1/billing/plans", cookies=C).json()
    names = [p["name"] for p in plans]
    assert names == ["Premium", "Enterprise"]

    premium = plans[0]
    assert premium["display_price"] == "$49"
    assert premium["worker_limit"] == 3
    assert "3 Digital Workers" in premium["features"]

    enterprise = plans[1]
    assert enterprise["display_price"] == "Custom Pricing"
    assert enterprise["worker_limit"] == -1
    assert "Dedicated Account Manager" in enterprise["features"]


def test_subscription_cancel_resume(client):
    client.post("/api/v1/billing/subscription/cus2/activate", json={"plan": "pro"}, cookies=C)
    assert client.post("/api/v1/billing/subscription/cus2/cancel", cookies=C).json()["cancel_at_period_end"] is True
    assert client.post("/api/v1/billing/subscription/cus2/resume", cookies=C).json()["cancel_at_period_end"] is False


def test_payment_links_admin_only(client):
    body = {"customer_email": "buyer@x.com", "amount_cents": 5000}
    assert client.post("/api/v1/billing/payment-links", json=body, cookies=auth_cookies("bill", "editor")).status_code == 403
    created = client.post("/api/v1/billing/payment-links", json=body, cookies=C).json()
    assert created["url"] and created["status"]
    assert client.get("/api/v1/billing/payment-links", params={"email": "buyer@x.com"}, cookies=C).json()
    assert client.post("/api/v1/billing/payment-links/mark-paid", json={"customer_email": "buyer@x.com"}, cookies=C).json()["marked"] >= 1


def test_mark_paid_missing_email_is_422_not_500(client):
    # Regression: mark-paid took a raw dict and did body["customer_email"], so a missing field
    # 500'd (unhandled KeyError) instead of returning a clean 422 validation error.
    r = client.post("/api/v1/billing/payment-links/mark-paid", json={}, cookies=C)
    assert r.status_code == 422


def test_team_plan_and_invoices(client):
    team = client.post("/api/v1/teams", json={"owner_id": "o"}, cookies=C).json()
    assert client.get(f"/api/v1/billing/team/{team['team_id']}/plan", cookies=C).json()["plan"] == "free"
    assert client.get("/api/v1/billing/invoices", cookies=C).json() == []


def test_team_plan_blocks_cross_tenant_access(client):
    # BOLA regression guard: another tenant must not be able to read bill's team billing plan
    # (which also discloses its member list) just by knowing/guessing its team_id.
    team = client.post("/api/v1/teams", json={"owner_id": "o"}, cookies=C).json()
    other = auth_cookies("billglobex", "owner")
    r = client.get(f"/api/v1/billing/team/{team['team_id']}/plan", cookies=other)
    assert r.status_code == 404
