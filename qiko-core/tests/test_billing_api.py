from tests.helpers import auth_cookies

C = auth_cookies("bill", "owner")


def test_checkout_and_portal(client):
    # Tenant-scoped: no client-supplied customer id -- the subject is the authed tenant.
    assert "url" in client.post("/api/v1/billing/checkout", json={"plan": "pro"}, cookies=C).json()
    assert "url" in client.get("/api/v1/billing/portal", cookies=C).json()


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
    # Lifecycle acts on the caller's own tenant (derived from auth), never a path/body id.
    client.post("/api/v1/billing/subscription/activate", json={"plan": "pro"}, cookies=C)
    assert client.get("/api/v1/billing/subscription", cookies=C).json()["status"] == "active"
    assert client.post("/api/v1/billing/subscription/cancel", cookies=C).json()["cancel_at_period_end"] is True
    assert client.post("/api/v1/billing/subscription/resume", cookies=C).json()["cancel_at_period_end"] is False


def test_subscription_is_tenant_scoped_no_cross_tenant_bola(client):
    """BOLA regression (OWASP A01/API1): a subscription's subject is the authenticated tenant,
    derived server-side -- there is no client-supplied id, so one tenant cannot read or act on
    another tenant's subscription.

    Tenant A ("bill") activates a subscription. Tenant B ("evilcorp"):
      * sees only its OWN (empty) subscription on GET /billing/subscription, never A's;
      * has no route/param to name A as the subject of cancel/resume -- those act on B alone and
        so 404/400 (B has nothing), leaving A's subscription untouched.
    """
    tenant_b = auth_cookies("evilcorp", "owner")

    # A activates.
    client.post("/api/v1/billing/subscription/activate", json={"plan": "pro"}, cookies=C)
    assert client.get("/api/v1/billing/subscription", cookies=C).json()["status"] == "active"

    # B reads its own status -> not A's; B has no subscription of its own.
    b_view = client.get("/api/v1/billing/subscription", cookies=tenant_b).json()
    assert b_view["status"] == "none"
    assert b_view["customer_id"] == "evilcorp"   # scoped to B, never "bill"

    # B cannot cancel/resume A's subscription: the endpoints only ever target B's own subject,
    # which doesn't exist -> 404 (cancel) / 400 (resume). No path or body lets B name "bill".
    assert client.post("/api/v1/billing/subscription/cancel", cookies=tenant_b).status_code == 404
    assert client.post("/api/v1/billing/subscription/resume", cookies=tenant_b).status_code == 400

    # A's subscription is still active and untouched by B's attempts.
    a_view = client.get("/api/v1/billing/subscription", cookies=C).json()
    assert a_view["status"] == "active" and a_view["cancel_at_period_end"] is False


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
