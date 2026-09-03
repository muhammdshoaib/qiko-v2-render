"""QIKO-1048 Phase 2: shape-parity tests for app/modules/billing/router.py.

Same methodology as Phase 1 (tests/test_admin_response_models.py): capture the exact current
response body before a response_model is attached, confirm it passes unmodified, add the model,
confirm the same test still passes.
"""
import json

from app.modules.billing.subscriptions import Subscription
from tests.helpers import auth_cookies


def _admin_cookies(tenant: str = "acme") -> dict:
    return auth_cookies(tenant, "admin")


def test_webhook_shape_when_signature_not_configured_and_debug_true(client):
    # In the test app, settings.debug defaults True and stripe_webhook_secret is unset, so the
    # route's "unverifiable webhook, but dev, so proceed" branch runs.
    body = json.dumps({"id": "", "type": "unknown.event", "data": {"object": {}}}).encode()
    res = client.post("/api/v1/billing/webhook/stripe", content=body,
                      headers={"content-type": "application/json"})
    assert res.status_code == 200
    assert set(res.json()) == {"action"}
    assert isinstance(res.json()["action"], str)


def test_subscription_status_shape_none_and_present(client):
    cookies = _admin_cookies()
    none_body = client.get("/api/v1/billing/subscription", cookies=cookies).json()
    assert none_body == {"customer_id": "acme", "status": "none"}

    client.app.state.subscriptions.store.put(Subscription(
        customer_id="acme", plan="pro", status="active", cancel_at_period_end=False))
    present_body = client.get("/api/v1/billing/subscription", cookies=cookies).json()
    assert set(present_body) == {"customer_id", "plan", "status", "cancel_at_period_end"}


def test_subscription_activate_shape(client):
    from app.core.config import get_settings

    assert get_settings().debug, "activate() 404s outside debug; the test app must run in debug"
    body = client.post("/api/v1/billing/subscription/activate", json={"plan": "pro"},
                       cookies=_admin_cookies()).json()
    assert set(body) == {"customer_id", "plan", "status"}


def test_subscription_cancel_and_resume_shape(client):
    cookies = _admin_cookies()
    client.app.state.subscriptions.store.put(Subscription(
        customer_id="acme", plan="pro", status="active", cancel_at_period_end=False))

    from app.modules.identity import csrf
    token = csrf.generate_csrf_token()
    with_csrf = {**cookies, csrf.CSRF_COOKIE: token}
    headers = {csrf.CSRF_HEADER: token}

    cancel_body = client.post("/api/v1/billing/subscription/cancel",
                              cookies=with_csrf, headers=headers).json()
    assert set(cancel_body) == {"customer_id", "status", "cancel_at_period_end"}

    resume_body = client.post("/api/v1/billing/subscription/resume",
                              cookies=with_csrf, headers=headers).json()
    assert set(resume_body) == {"customer_id", "status", "cancel_at_period_end"}


def test_plans_shape(client):
    body = client.get("/api/v1/billing/plans").json()
    assert body, "list_plans() must return at least one plan for this assertion to mean anything"
    assert set(body[0]) == {
        "key", "id", "name", "display_name", "price_id", "amount", "interval",
        "display_price", "worker_limit", "features",
    }


def test_checkout_and_portal_shape(client):
    from app.modules.identity import csrf

    cookies = _admin_cookies("bill")
    token = csrf.generate_csrf_token()
    with_csrf = {**cookies, csrf.CSRF_COOKIE: token}
    headers = {csrf.CSRF_HEADER: token, "origin": "http://localhost:3000"}

    checkout_body = client.post("/api/v1/billing/checkout", json={"plan": "pro"},
                                cookies=with_csrf, headers=headers).json()
    assert set(checkout_body) == {"url"}

    portal_body = client.get("/api/v1/billing/portal", cookies=cookies).json()
    assert set(portal_body) == {"url"}


def test_team_plan_shape(client):
    # team_billing_plan has no role dependency at all (any authenticated tenant member can read
    # it) - team CREATION is what test_billing_api.py's test_team_plan_and_invoices seeds with
    # tenant role "owner" specifically, so match that exactly here.
    owner_cookies = auth_cookies("bill", "owner")
    body = client.post("/api/v1/teams", json={"owner_id": "o"}, cookies=owner_cookies).json()
    plan_body = client.get(f"/api/v1/billing/team/{body['team_id']}/plan",
                           cookies=owner_cookies).json()
    assert set(plan_body) == {"team_id", "plan"}


def _billing_admin_cookies(client) -> dict:
    """A platform super_admin (bootstrap_admin grants every Capability, including
    manage_billing) - same pattern as tests/test_billing_api.py's own _admin_cookies helper for
    the payment-link and invoice routes, which are gated on Capability.manage_billing, not the
    tenant-role checks the other billing tests in this file use."""
    from tests.helpers import bootstrap_admin

    email = "billing-response-models@invalid"
    bootstrap_admin(client, email)
    return auth_cookies("platform", "viewer", email=email)


def test_create_and_list_and_mark_paid_payment_links_shape(client):
    from app.modules.identity import csrf

    admin = _billing_admin_cookies(client)
    create_token = csrf.generate_csrf_token()
    created = client.post(
        "/api/v1/billing/payment-links",
        json={"customer_email": "buyer@x.com", "amount_cents": 5000},
        cookies={**admin, csrf.CSRF_COOKIE: create_token},
        headers={csrf.CSRF_HEADER: create_token}).json()
    assert set(created) == {"session_id", "url", "status"}

    listed = client.get("/api/v1/billing/payment-links", params={"email": "buyer@x.com"},
                        cookies=admin).json()
    assert listed, "the created link above must appear in the list"
    assert set(listed[0]) == {"session_id", "customer_email", "amount_cents", "url", "status"}

    mark_token = csrf.generate_csrf_token()
    marked = client.post("/api/v1/billing/payment-links/mark-paid",
                         json={"customer_email": "buyer@x.com"},
                         cookies={**admin, csrf.CSRF_COOKIE: mark_token},
                         headers={csrf.CSRF_HEADER: mark_token}).json()
    assert set(marked) == {"marked"}


def test_invoices_list_and_create_shape(client):
    from app.modules.billing.webhook import Invoice
    from app.modules.identity import csrf
    from tests.helpers import bootstrap_admin

    client.app.state.stripe_webhook.invoices.upsert(Invoice(
        stripe_invoice_id="in_1", customer_id="acme", amount_cents=5000, status="paid"))

    email = "invoices-response-models@invalid"
    bootstrap_admin(client, email)
    admin = auth_cookies("platform", "viewer", email=email)

    listed = client.get("/api/v1/billing/invoices", cookies=admin).json()
    assert set(listed) == {"total", "page", "page_size", "items"}
    assert listed["items"], "the seeded invoice above must appear in the list"
    assert set(listed["items"][0]) == {
        "stripe_invoice_id", "customer_id", "amount_cents", "status", "currency",
        "number", "hosted_invoice_url", "invoice_pdf", "period_start", "period_end",
    }

    create_token = csrf.generate_csrf_token()
    created = client.post(
        "/api/v1/billing/invoices",
        json={"customer_id": "cus_test", "amount_cents": 1000, "currency": "usd"},
        cookies={**admin, csrf.CSRF_COOKIE: create_token},
        headers={csrf.CSRF_HEADER: create_token}).json()
    assert set(created) == set(listed["items"][0])


def test_invoices_reconcile_shape(client):
    from app.modules.identity import csrf
    from tests.helpers import bootstrap_admin

    email = "reconcile-response-models@invalid"
    bootstrap_admin(client, email)
    admin = auth_cookies("platform", "viewer", email=email)
    reconcile_token = csrf.generate_csrf_token()

    body = client.post("/api/v1/billing/invoices/reconcile",
                       cookies={**admin, csrf.CSRF_COOKIE: reconcile_token},
                       headers={csrf.CSRF_HEADER: reconcile_token}).json()
    assert set(body) == {"open", "recent"}
