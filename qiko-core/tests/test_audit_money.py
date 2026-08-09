"""Wave 1 of audit coverage: money.

Nothing recorded who moved or claimed money. An operator could create a Stripe payment link, email it
to a customer, and mark it paid without a payment ever arriving, and the only trace anywhere was a
created_at on the link row with no actor at all.
"""


from app.modules.audit import registry
from app.modules.identity import csrf
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN = "money-admin.invalid"


def _admin(client) -> tuple[dict, dict]:
    bootstrap_admin(client, ADMIN)
    cookies = auth_cookies("platform", "owner", email=ADMIN)
    token = csrf.generate_csrf_token()
    return {**cookies, csrf.CSRF_COOKIE: token}, {csrf.CSRF_HEADER: token}


def _events(client, cookies) -> list[dict]:
    return client.get("/api/v1/admin/audit?days=1&limit=200",
                      cookies={k: v for k, v in cookies.items() if k != csrf.CSRF_COOKIE}).json()["items"]


def test_creating_a_payment_link_records_the_attempt_and_the_outcome(client):
    cookies, headers = _admin(client)
    response = client.post("/api/v1/billing/payment-links", cookies=cookies, headers=headers,
                           json={"customer_email": "payer@acme.invalid", "amount_cents": 4200})
    assert response.status_code == 200

    actions = [e["action"] for e in _events(client, cookies)]
    assert registry.PAYMENT_LINK_ATTEMPTED in actions
    assert registry.PAYMENT_LINK_CREATED in actions
    created = next(e for e in _events(client, cookies)
                   if e["action"] == registry.PAYMENT_LINK_CREATED)
    assert created["actor_label"] == ADMIN
    assert created["changes"]["amount_cents"]["to"] == 4200
    assert created["outcome"] == "success"


def test_a_provider_failure_is_recorded_rather_than_only_raised(client, monkeypatch):
    """The link may exist and the customer may already have been emailed. An attempt with no outcome,
    or an explicit failure, is what sends an operator to check."""
    import httpx

    from app.core import deps

    class Failing:
        def create(self, *_args, **_kwargs):
            raise httpx.ConnectError("stripe unreachable")

        def logs_for(self, _email):
            return []

    cookies, headers = _admin(client)
    client.app.dependency_overrides[deps.get_payment_links] = lambda: Failing()
    try:
        response = client.post("/api/v1/billing/payment-links", cookies=cookies, headers=headers,
                               json={"customer_email": "payer@acme.invalid", "amount_cents": 900})
        assert response.status_code == 502
    finally:
        client.app.dependency_overrides.pop(deps.get_payment_links, None)

    events = _events(client, cookies)
    assert any(e["action"] == registry.PAYMENT_LINK_ATTEMPTED for e in events)
    failure = next(e for e in events if e["action"] == registry.PAYMENT_LINK_CREATED)
    assert failure["outcome"] == "failure"
    assert failure["metadata"]["error"] == "ConnectError"


def test_marking_a_link_paid_is_recorded(client):
    """An operator declaring money received without money moving. If one row in this table ever
    matters in a dispute, it is this one."""
    cookies, headers = _admin(client)
    client.post("/api/v1/billing/payment-links", cookies=cookies, headers=headers,
                json={"customer_email": "payer@acme.invalid", "amount_cents": 4200})
    response = client.post("/api/v1/billing/payment-links/mark-paid", cookies=cookies,
                           headers=headers, json={"customer_email": "payer@acme.invalid"})
    assert response.status_code == 200

    marked = next(e for e in _events(client, cookies)
                  if e["action"] == registry.PAYMENT_LINK_MARKED_PAID)
    assert marked["actor_label"] == ADMIN
    assert marked["changes"]["status"] == {"from": "pending", "to": "paid"}
    assert marked["target_id"] == "payer@acme.invalid"


def test_money_events_are_hidden_from_an_admin_without_manage_billing(client):
    """Amounts and customer emails are commercial detail, so the read gate matches the one on the
    billing endpoints themselves."""
    cookies, headers = _admin(client)
    client.post("/api/v1/billing/payment-links", cookies=cookies, headers=headers,
                json={"customer_email": "payer@acme.invalid", "amount_cents": 4200})

    from app.modules.identity.admin_rbac import Capability

    # view_audit is what permits reading the trail at all; view_ai_cost and manage_billing are what
    # gate the amounts inside it. This reader gets the first and neither of the others.
    client.put("/api/v1/admin/org/nobilling@invalid", cookies=cookies, headers=headers,
               json={"role": "viewer", "capabilities": [Capability.view_customers.value,
                                                       Capability.view_audit.value]})
    narrow = auth_cookies("platform", "viewer", email="nobilling@invalid")
    visible = client.get("/api/v1/admin/audit?days=1", cookies=narrow).json()
    assert all(not e["action"].startswith("billing.") for e in visible["items"])
    assert visible["hidden_actions"] > 0, "the reader should be told events exist that they cannot see"


def test_the_audit_write_never_breaks_the_payment(client, monkeypatch):
    """A failed audit insert must not turn a created payment link into a 500: the link exists and the
    customer has been emailed, so reporting failure would have an operator create a second one."""
    cookies, headers = _admin(client)

    def explode(_row):
        raise RuntimeError("audit table is gone")

    monkeypatch.setattr(client.app.state.audit, "add_sync", explode)
    response = client.post("/api/v1/billing/payment-links", cookies=cookies, headers=headers,
                           json={"customer_email": "payer@acme.invalid", "amount_cents": 100})
    assert response.status_code == 200
