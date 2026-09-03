"""QIKO-1048 Phase 1: shape-parity tests for admin response models.

Each test in this file (and its siblings added by later tasks in this plan) captures the
EXACT current response body of one route before a response_model is attached to it, then is
re-run unchanged after the model is added. If a shape-parity test needs to change to keep
passing once a response_model exists, the model is wrong, not the test.
"""
from app.modules.admin.pagination import PaginatedOut
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import Capability
from tests.helpers import auth_cookies, bootstrap_admin


def test_paginated_out_is_generic_and_resolves_a_distinct_schema_per_item_type():
    from pydantic import BaseModel

    class Row(BaseModel):
        name: str

    page = PaginatedOut[Row](total=1, page=1, page_size=20, items=[Row(name="a")])
    assert page.model_dump() == {
        "total": 1, "page": 1, "page_size": 20, "items": [{"name": "a"}],
    }
    # FastAPI must resolve response_model=PaginatedOut[Row] into a schema named after Row, not
    # a shared ambiguous "PaginatedOut" schema every concretization overwrites.
    schema = PaginatedOut[Row].model_json_schema()
    assert "Row" in str(schema)


def _admin(client) -> dict:
    """A super_admin's cookies (bootstrap_admin grants every Capability by default - see
    admin_rbac.py's _DEFAULTS). Use this when a test does not care which specific capability
    gates the route. Use _grant below when a test needs to exercise a NARROWER capability set."""
    email = "response-models-admin.invalid"
    bootstrap_admin(client, email)
    return auth_cookies("t", "viewer", email=email)


def _csrf(cookies: dict) -> tuple[dict, dict]:
    token = csrf.generate_csrf_token()
    return {**cookies, csrf.CSRF_COOKIE: token}, {csrf.CSRF_HEADER: token}


def _grant(client, email: str, capabilities: list[str]) -> tuple[dict, dict]:
    """Cookies (already paired with a matching CSRF header/cookie) for an admin holding exactly
    these capabilities, none more. Same pattern as tests/test_admin_support_worker.py's _grant."""
    root_cookies, root_headers = _csrf(_admin(client))
    client.put(f"/api/v1/admin/org/{email}", cookies=root_cookies, headers=root_headers,
              json={"role": "viewer", "capabilities": capabilities})
    return _csrf(auth_cookies("platform", "viewer", email=email))


def test_revenue_shape(client):
    from app.modules.billing.webhook import Invoice
    from app.modules.billing.subscriptions import Subscription

    client.app.state.stripe_webhook.invoices.upsert(Invoice(
        stripe_invoice_id="in_1", customer_id="acme", amount_cents=5000, status="paid"))
    client.app.state.subscriptions.store.put(Subscription(
        customer_id="acme", plan="pro", status="active"))

    admin = _admin(client)
    body = client.get("/api/v1/admin/revenue", cookies=admin).json()
    assert set(body) == {
        "total_paid_cents", "outstanding_cents", "mrr_cents", "arr_cents",
        "active_subscriptions", "by_plan", "monthly",
    }
    assert body["total_paid_cents"] == 5000
    assert body["active_subscriptions"] == 1
    assert body["by_plan"] == {"pro": 1}
    assert isinstance(body["monthly"], list)
    if body["monthly"]:
        assert set(body["monthly"][0]) == {"month", "paid_cents"}


def test_customers_list_shape(client):
    from app.modules.admin.customers import CustomerRecord

    client.app.state.customers.add(CustomerRecord("u1", "a@x.com", "pro",
                                                   stripe_paid_cents=1000))
    admin = _admin(client)
    body = client.get("/api/v1/admin/customers", cookies=admin).json()
    assert set(body) == {"total", "page", "page_size", "items"}
    assert set(body["items"][0]) == {"user_id", "email", "plan", "earnings_cents"}


def test_overview_shape(client):
    admin = _admin(client)
    body = client.get("/api/v1/admin/overview", cookies=admin).json()
    assert set(body) == {"customers_total", "active_subscriptions", "by_plan"}
    assert isinstance(body["by_plan"], dict)


def test_analytics_shape_when_ga4_unavailable(client):
    admin = _admin(client)
    body = client.get("/api/v1/admin/analytics", cookies=admin).json()
    assert body == {"sessions": 0, "active_users": 0, "top_pages": [], "had_data": False}


def test_tenants_shape_matches_existing_model(client):
    from app.modules.admin.customers import CustomerRecord
    from app.modules.admin.router import TenantDirectoryRow

    client.app.state.customers.add(CustomerRecord("u1", "a@x.com", "pro", agents=2, users=3))
    admin = _admin(client)
    body = client.get("/api/v1/admin/tenants", cookies=admin).json()
    assert set(body["items"][0]) == set(TenantDirectoryRow.model_fields)


def test_users_shape_matches_existing_model(client):
    import asyncio
    from app.core.deps import get_user_store
    from app.modules.identity.rbac import Role
    from app.modules.identity.store import User
    from app.modules.admin.router import UserDirectoryRow

    asyncio.run(get_user_store().add(User(id="u1", email="dir-user@acme.invalid",
                                          password_hash="x", tenant="acme", role=Role.editor)))
    admin = _admin(client)
    body = client.get("/api/v1/admin/users", cookies=admin).json()
    assert body["items"], "the seeded user above must appear in the directory"
    assert set(body["items"][0]) == set(UserDirectoryRow.model_fields)


def test_workers_shape_matches_existing_model(client):
    import asyncio
    from app.modules.agents.service import Agent
    from app.modules.admin.router import WorkerDirectoryRow

    asyncio.run(client.app.state.agents.store.add(Agent(id="a1", tenant="acme", name="A")))
    admin = _admin(client)
    body = client.get("/api/v1/admin/workers", cookies=admin).json()
    assert set(body["items"][0]) == set(WorkerDirectoryRow.model_fields)


def test_ai_cost_shape(client):
    admin = _admin(client)
    body = client.get("/api/v1/admin/ai-cost", cookies=admin).json()
    assert set(body) == {"window_days", "totals", "tenant", "model", "operation", "day"}
    assert set(body["totals"]) == {
        "calls", "input_tokens", "output_tokens", "cost_nano_usd", "unpriced_calls",
    }
    for breakdown_name in ("tenant", "model", "operation", "day"):
        assert isinstance(body[breakdown_name], dict)
        for totals in body[breakdown_name].values():
            assert set(totals) == {
                "calls", "input_tokens", "output_tokens", "cost_nano_usd", "unpriced_calls",
            }


def test_worker_monitoring_shape_with_and_without_cost_capability(client):
    import asyncio
    from app.modules.agents.service import Agent

    asyncio.run(client.app.state.agents.store.add(Agent(id="a1", tenant="acme", name="A")))

    # bootstrap_admin's caller is a super_admin (every Capability, including view_ai_cost) -
    # exercises the cost_visible=True branch.
    with_cost = _admin(client)
    body = client.get("/api/v1/admin/worker-monitoring", cookies=with_cost).json()
    assert set(body) == {"total", "page", "page_size", "window_days", "cost_visible", "items"}
    assert body["cost_visible"] is True
    row = body["items"][0]
    assert {"cost_nano_usd", "input_tokens", "output_tokens"} <= set(row)
    # last_seen is not capability-gated - it must survive regardless (this worker has no usage
    # summary yet, so it is genuinely null, not merely absent).
    assert "last_seen" in row and row["last_seen"] is None

    # Narrower grant, view_customers only (no view_ai_cost) - exercises cost_visible=False.
    cookies, _ = _grant(client, "monitoring-no-cost@invalid", [Capability.view_customers.value])
    narrow_body = client.get("/api/v1/admin/worker-monitoring", cookies=cookies).json()
    assert narrow_body["cost_visible"] is False
    narrow_row = narrow_body["items"][0]
    # The 3 cost fields are omitted entirely (not merely null) for a caller without
    # view_ai_cost - exact pre-model behavior, preserved via a JSONResponse bypass in the route
    # (see its docstring) rather than response_model_exclude_none, which would also have
    # dropped the always-present last_seen field below.
    assert not ({"cost_nano_usd", "input_tokens", "output_tokens"} & set(narrow_row))
    assert "last_seen" in narrow_row and narrow_row["last_seen"] is None


def test_cost_caps_list_and_set_and_delete_shape(client):
    cookies, headers = _grant(client, "capcaps@invalid",
                              [Capability.view_ai_cost.value, Capability.set_cost_caps.value])
    body = client.get("/api/v1/admin/cost-caps", cookies=cookies).json()
    assert set(body) == {"platform_key", "items"}

    put = client.put("/api/v1/admin/cost-caps/acme", json={"monthly_cap_usd": 10.0},
                     cookies=cookies, headers=headers)
    assert set(put.json()) == {
        "tenant_id", "agent_id", "monthly_cap_nano_usd", "unlimited",
        "alert_threshold_pct", "updated_by_email", "updated_at",
    }

    deleted = client.delete("/api/v1/admin/cost-caps/acme", cookies=cookies, headers=headers)
    assert set(deleted.json()) == {"removed", "agent_id"}


def test_set_tenant_role_shape(client):
    import asyncio
    from app.core.deps import get_user_store
    from app.modules.identity.rbac import Role
    from app.modules.identity.store import User

    async def seed():
        store = get_user_store()
        await store.add(User(id="u2", email="editor@acme.invalid", password_hash="x",
                             tenant="acme", role=Role.editor))
    asyncio.run(seed())

    cookies, headers = _grant(client, "roles@invalid", [Capability.manage_customers.value])
    body = client.put("/api/v1/admin/users/u2/role", json={"role": "admin"},
                      cookies=cookies, headers=headers).json()
    assert set(body) == {"id", "email", "tenant_id", "role", "role_label", "previous_role"}


def test_set_worker_status_shape(client):
    import asyncio
    from app.modules.agents.service import Agent

    asyncio.run(client.app.state.agents.store.add(
        Agent(id="a1", tenant="acme", name="A", status="ready")))
    cookies, headers = _grant(client, "workerstatus@invalid", [Capability.manage_workers.value])
    body = client.put("/api/v1/admin/workers/acme/a1/status", json={"status": "training"},
                      cookies=cookies, headers=headers).json()
    assert set(body) == {
        "id", "name", "type", "status", "enabled", "created_at", "config",
        "tenant_id", "changed",
    }


def test_audit_list_shape(client):
    import asyncio
    from app.modules.agents.service import Agent

    # A real mutation (rather than writing a row to the store directly) produces exactly the
    # shape the audit list route actually reads, including every field build_row() sets.
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="a1", tenant="acme", name="A", status="ready")))
    cookies, headers = _csrf(_admin(client))
    client.put("/api/v1/admin/workers/acme/a1/status", json={"status": "training"},
              cookies=cookies, headers=headers)

    body = client.get("/api/v1/admin/audit", cookies=cookies).json()
    assert set(body) == {"items", "next_cursor", "has_more", "window_days", "hidden_actions"}
    assert body["items"], "the status-change mutation above must have produced at least one row"
    row = body["items"][0]
    assert set(row) == {
        "event_id", "action", "category", "outcome", "message", "occurred_at",
        "actor_type", "actor_id", "actor_label", "on_behalf_of", "target_type",
        "target_id", "target_label", "tenant_id", "request_id", "source_ip",
        "user_agent", "route", "service", "environment", "changes", "metadata",
        "reason", "_cursor",
    }


def test_audit_action_catalogue_shape(client):
    admin = _admin(client)
    body = client.get("/api/v1/admin/audit/actions", cookies=admin).json()
    assert set(body) == {"categories", "actions"}
    assert set(body["actions"][0]) == {"action", "category", "target_type"}


def test_audit_erase_shape(client):
    cookies, headers = _csrf(_admin(client))
    res = client.post("/api/v1/admin/audit/erase",
                      json={"identifier": "someone@x.com", "request_ref": "DSAR-1"},
                      cookies=cookies, headers=headers)
    assert res.status_code == 202
    assert set(res.json()) == {"pseudonym", "request_ref", "status", "where_to_check"}


def test_audit_retention_shape(client):
    admin = _admin(client)
    body = client.get("/api/v1/admin/audit/retention", cookies=admin).json()
    assert set(body) == {
        "event_retention_days", "network_retention_days", "erasure", "archive",
    }


def test_system_shape(client):
    admin = _admin(client)
    body = client.get("/api/v1/admin/system", cookies=admin).json()
    assert set(body) == {
        "ready", "checks", "process", "database", "redis", "queue", "environment", "version",
    }
    assert set(body["database"]) >= {"available"}
    assert set(body["redis"]) >= {"available"}
    assert set(body["queue"]) >= {"available"}
    if body["checks"]:
        assert set(body["checks"][0]) == {"name", "ok", "detail", "latency_ms"}
