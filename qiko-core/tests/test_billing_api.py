import asyncio

from app.core.config import Environment, get_settings
from app.modules.identity.admin_rbac import AdminRole
from tests.helpers import auth_cookies, bootstrap_admin

C = auth_cookies("bill", "owner")
ADMIN_EMAIL = "billing-admin" + "@" + "example.com"


def _admin_cookies(client):
    bootstrap_admin(client, ADMIN_EMAIL)
    return auth_cookies("platform", "viewer", email=ADMIN_EMAIL)


def _platform_viewer_cookies(client):
    async def create_viewer():
        await client.app.state.admin_org.bootstrap_super_admin(ADMIN_EMAIL)
        token = await client.app.state.admin_org.invite(
            ADMIN_EMAIL, "billing-viewer" + "@" + "example.com", AdminRole.viewer)
        await client.app.state.admin_org.accept(token)

    asyncio.run(create_viewer())
    return auth_cookies("platform", "viewer", email="billing-viewer" + "@" + "example.com")


def test_checkout_and_portal(client):
    # Tenant-scoped: no client-supplied customer id -- the subject is the authed tenant.
    assert "url" in client.post("/api/v1/billing/checkout", json={"plan": "pro"}, cookies=C).json()
    assert "url" in client.get("/api/v1/billing/portal", cookies=C).json()


def test_paid_activation_disabled_and_checkout_unavailable_outside_dev(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", Environment.preprod)
    monkeypatch.setattr(settings, "stripe_price_pro", "")  # not provisioned

    # Direct activate stays dev-only (404). Checkout no longer 404s: without a configured Stripe price
    # it fails closed with a clear 503 (not a broken redirect) so the UI can show "unavailable".
    assert client.post("/api/v1/billing/subscription/activate", json={"plan": "pro"}, cookies=C).status_code == 404
    assert client.post("/api/v1/billing/checkout", json={"plan": "pro"}, cookies=C).status_code == 503


def test_checkout_uses_configured_price_outside_dev(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", Environment.preprod)
    monkeypatch.setattr(settings, "stripe_price_pro", "price_live_123")  # provisioned in SSM

    res = client.post("/api/v1/billing/checkout", json={"plan": "pro"}, cookies=C)
    assert res.status_code == 200 and "url" in res.json()

    # Price tampering is prevented: a client-supplied price_id is ignored; the server-configured
    # price is used (the stub checkout URL reflects the price it was given).
    tampered = client.post("/api/v1/billing/checkout",
                           json={"plan": "pro", "price_id": "price_attacker"}, cookies=C)
    assert tampered.status_code == 200
    url = tampered.json()["url"]
    assert "price_live_123" in url and "price_attacker" not in url

    # Enterprise is contact-sales: not self-serve checkout even when Stripe is configured.
    assert client.post("/api/v1/billing/checkout", json={"plan": "enterprise"}, cookies=C).status_code == 503


def test_billing_lifecycle_requires_tenant_admin_or_owner(client):
    for role in ("viewer", "editor"):
        cookies = auth_cookies("bill", role)
        assert client.get("/api/v1/billing/subscription", cookies=cookies).status_code == 403
        assert client.get("/api/v1/billing/portal", cookies=cookies).status_code == 403
        assert client.post("/api/v1/billing/subscription/cancel", cookies=cookies).status_code == 403
        assert client.post("/api/v1/billing/subscription/resume", cookies=cookies).status_code == 403


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


def test_payment_links_require_platform_admin(client):
    body = {"customer_email": "buyer" + "@" + "example.com", "amount_cents": 5000}
    assert client.post("/api/v1/billing/payment-links", json=body, cookies=C).status_code == 403
    admin = {**_admin_cookies(client), "qiko_csrf": "csrf-test"}
    headers = {"x-csrf-token": "csrf-test", "origin": "http://testserver"}
    created = client.post("/api/v1/billing/payment-links", json=body, cookies=admin, headers=headers).json()
    assert created["url"] and created["status"]
    assert client.get("/api/v1/billing/payment-links", params={"email": "buyer" + "@" + "example.com"}, cookies=admin).json()
    assert client.post("/api/v1/billing/payment-links/mark-paid",
                       json={"customer_email": "buyer" + "@" + "example.com"}, cookies=admin, headers=headers).json()["marked"] >= 1


def test_platform_viewer_cannot_mutate_payment_links(client):
    viewer = _platform_viewer_cookies(client)
    body = {"customer_email": "buyer" + "@" + "example.com", "amount_cents": 5000}
    assert client.post("/api/v1/billing/payment-links", json=body, cookies=viewer).status_code == 403
    assert client.post("/api/v1/billing/payment-links/mark-paid",
                       json={"customer_email": "buyer" + "@" + "example.com"}, cookies=viewer).status_code == 403


def test_recurring_payment_link_is_rejected_until_stripe_support_is_wired(client):
    response = client.post(
        "/api/v1/billing/payment-links",
        json={"customer_email": "buyer" + "@" + "example.com", "amount_cents": 5000, "recurring": True},
        cookies=_admin_cookies(client),
    )
    assert response.status_code == 422


def test_payment_link_amount_is_positive_and_bounded(client):
    admin = _admin_cookies(client)
    for amount in (0, -1, 100_000_001):
        response = client.post(
            "/api/v1/billing/payment-links",
            json={"customer_email": "buyer" + "@" + "example.com", "amount_cents": amount},
            cookies=admin,
        )
        assert response.status_code == 422


def test_mark_paid_missing_email_is_422_not_500(client):
    # Regression: mark-paid took a raw dict and did body["customer_email"], so a missing field
    # 500'd (unhandled KeyError) instead of returning a clean 422 validation error.
    r = client.post("/api/v1/billing/payment-links/mark-paid", json={}, cookies=_admin_cookies(client))
    assert r.status_code == 422


def test_team_plan_and_invoices(client):
    team = client.post("/api/v1/teams", json={"owner_id": "o"}, cookies=C).json()
    assert client.get(f"/api/v1/billing/team/{team['team_id']}/plan", cookies=C).json()["plan"] == "free"
    assert client.get("/api/v1/billing/invoices", cookies=C).status_code == 403
    # The shape is the directory shape now: total, page, page_size, items. It returned a bare array,
    # which is fine for one customer and unusable after a year of monthly invoices across a hundred
    # accounts, and it was the last list in the console that behaved that way.
    body = client.get("/api/v1/billing/invoices", cookies=_admin_cookies(client)).json()
    assert body == {"total": 0, "page": 1, "page_size": 20, "items": []}


def test_team_plan_blocks_cross_tenant_access(client):
    # BOLA regression guard: another tenant must not be able to read bill's team billing plan
    # (which also discloses its member list) just by knowing/guessing its team_id.
    team = client.post("/api/v1/teams", json={"owner_id": "o"}, cookies=C).json()
    other = auth_cookies("billglobex", "owner")
    r = client.get(f"/api/v1/billing/team/{team['team_id']}/plan", cookies=other)
    assert r.status_code == 404


def _seed_invoices(client, count: int = 25) -> None:
    from app.modules.billing.webhook import Invoice

    for index in range(count):
        client.app.state.stripe_webhook.invoices.upsert(Invoice(
            stripe_invoice_id=f"in_{index:03d}", customer_id=f"cus_{index % 4}",
            amount_cents=(index + 1) * 500,
            status="paid" if index % 3 else "open"))


def test_invoices_paginate_like_every_other_directory(client):
    """A page that loads every invoice and offers no way to find one is not a list, it is a dump."""
    _seed_invoices(client)
    admin = _admin_cookies(client)

    first = client.get("/api/v1/billing/invoices?page_size=10", cookies=admin).json()
    assert first["total"] == 25 and first["page_size"] == 10 and len(first["items"]) == 10

    last = client.get("/api/v1/billing/invoices?page_size=10&page=3", cookies=admin).json()
    assert len(last["items"]) == 5, "the short final page is where an off-by-one shows up"


def test_invoices_sort_only_by_keys_the_allowlist_names(client):
    """Shared with the admin directories deliberately: a second sorting implementation is a second place
    for the "unknown key falls back silently" bug the allowlist exists to prevent."""
    _seed_invoices(client, 5)
    admin = _admin_cookies(client)

    by_amount = client.get("/api/v1/billing/invoices?sort=amount&order=desc", cookies=admin).json()
    assert [i["amount_cents"] for i in by_amount["items"]] == [2500, 2000, 1500, 1000, 500]

    # An unknown key is refused rather than quietly ignored, or the operator believes a sort happened.
    assert client.get("/api/v1/billing/invoices?sort=customer_secret",
                      cookies=admin).status_code == 422


def test_invoices_can_be_searched_and_filtered(client):
    _seed_invoices(client)
    admin = _admin_cookies(client)

    assert client.get("/api/v1/billing/invoices?search=in_007",
                      cookies=admin).json()["total"] == 1
    # Search covers the customer too, because "which invoices does this account have" is the question
    # actually being asked when somebody types into that box.
    assert client.get("/api/v1/billing/invoices?search=cus_1", cookies=admin).json()["total"] > 1
    open_only = client.get("/api/v1/billing/invoices?status=open", cookies=admin).json()
    assert open_only["total"] > 0
    assert all(i["status"] == "open" for i in open_only["items"])


def test_the_invoice_list_still_needs_manage_billing(client):
    """Pagination must not have widened who can read it."""
    _seed_invoices(client, 2)
    assert client.get("/api/v1/billing/invoices", cookies=C).status_code == 403
