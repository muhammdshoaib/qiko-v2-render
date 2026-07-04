from tests.helpers import auth_cookies

C = auth_cookies("bill", "owner")


def test_checkout_and_portal(client):
    assert "url" in client.post("/api/v1/billing/checkout", json={"customer_id": "cus1", "plan": "pro"}, cookies=C).json()
    assert "url" in client.get("/api/v1/billing/portal/cus1", cookies=C).json()


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


def test_team_plan_and_invoices(client):
    team = client.post("/api/v1/teams", json={"owner_id": "o"}, cookies=C).json()
    assert client.get(f"/api/v1/billing/team/{team['team_id']}/plan", cookies=C).json()["plan"] == "free"
    assert client.get("/api/v1/billing/invoices", cookies=C).json() == []
