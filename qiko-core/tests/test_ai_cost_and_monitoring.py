"""QIK-517 platform AI spend and QIK-521 worker monitoring.

Both read the events QIK-514 records. Before this there was no way to answer "what is this customer
costing us" or "is this worker alive and being used" without opening records one at a time and
inferring it from nothing.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.agents.service import Agent
from app.modules.ai import usage
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import Capability
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN = "cost-admin.invalid"
NOW = datetime.now(timezone.utc)


def _admin(client) -> dict:
    bootstrap_admin(client, ADMIN)
    return auth_cookies("platform", "viewer", email=ADMIN)


def _grant(client, email: str, capabilities: list[str]) -> dict:
    cookies = _admin(client)
    token = csrf.generate_csrf_token()
    client.put(f"/api/v1/admin/org/{email}",
               cookies={**cookies, csrf.CSRF_COOKIE: token},
               headers={csrf.CSRF_HEADER: token},
               json={"role": "viewer", "capabilities": capabilities})
    return auth_cookies("platform", "viewer", email=email)


def _event(tenant, agent, *, when=None, cost=1_000_000, model="anthropic.claude-sonnet-4-5",
           operation="generate", priced=True, calls_in=100, calls_out=20):
    return usage.UsageEvent(tenant=tenant, agent_id=agent, model_id=model, operation=operation,
                            input_tokens=calls_in, output_tokens=calls_out, cost_nano_usd=cost,
                            created_at=when or NOW, priced=priced)


def _seed(client) -> None:
    async def seed() -> None:
        await client.app.state.agents.store.add(Agent(id="a1", tenant="acme", name="Busy worker"))
        await client.app.state.agents.store.add(Agent(id="a2", tenant="acme", name="Idle worker"))
        await client.app.state.agents.store.add(Agent(id="b1", tenant="beta", name="Beta worker",
                                                     enabled=False))
        await client.app.state.ai_usage.add_many([
            _event("acme", "a1", cost=3_000_000),
            _event("acme", "a1", cost=1_000_000, operation="embed",
                   model="amazon.titan-embed-text-v2:0"),
            _event("beta", "b1", cost=500_000),
            _event("acme", None, cost=250_000),                      # unattributed worker
            _event("acme", "a1", cost=0, model="some.future-model", priced=False),
            _event("acme", "a1", cost=9_000_000, when=NOW - timedelta(days=90)),  # outside 30d
        ])

    asyncio.run(seed())


# --- QIK-517 platform spend -----------------------------------------------------------------------

def test_platform_spend_totals_and_breakdowns(client):
    _seed(client)
    body = client.get("/api/v1/admin/ai-cost?days=30", cookies=_admin(client)).json()

    assert body["window_days"] == 30
    # the 90-day-old event is excluded by the window
    assert body["totals"]["cost_nano_usd"] == 3_000_000 + 1_000_000 + 500_000 + 250_000
    assert body["totals"]["calls"] == 5
    assert body["tenant"]["acme"]["cost_nano_usd"] == 3_000_000 + 1_000_000 + 250_000
    assert body["tenant"]["beta"]["cost_nano_usd"] == 500_000
    assert body["operation"]["embed"]["calls"] == 1
    assert "anthropic.claude-sonnet-4-5" in body["model"]
    assert NOW.date().isoformat() in body["day"]


def test_unpriced_spend_is_surfaced_not_hidden(client):
    """A model with no published rate contributes zero cost. Reporting the total without saying so
    would understate spend while looking authoritative."""
    _seed(client)
    body = client.get("/api/v1/admin/ai-cost", cookies=_admin(client)).json()
    assert body["totals"]["unpriced_calls"] == 1


def test_unattributed_spend_still_reconciles_with_the_total(client):
    """AWS billed it, so it must appear somewhere rather than being dropped."""
    _seed(client)
    body = client.get("/api/v1/admin/ai-cost", cookies=_admin(client)).json()
    per_tenant = sum(row["cost_nano_usd"] for row in body["tenant"].values())
    assert per_tenant == body["totals"]["cost_nano_usd"]


def test_the_window_is_bounded(client):
    cookies = _admin(client)
    assert client.get("/api/v1/admin/ai-cost?days=0", cookies=cookies).status_code == 422
    assert client.get("/api/v1/admin/ai-cost?days=100000", cookies=cookies).status_code == 422


def test_spend_needs_view_ai_cost_specifically(client):
    _seed(client)
    reader = _grant(client, "customers.only@invalid", [Capability.view_customers.value])
    assert client.get("/api/v1/admin/ai-cost", cookies=reader).status_code == 403
    assert client.get("/api/v1/admin/tenants", cookies=reader).status_code == 200

    coster = _grant(client, "cost.only@invalid", [Capability.view_ai_cost.value])
    assert client.get("/api/v1/admin/ai-cost", cookies=coster).status_code == 200
    # and it does not thereby gain the customer directory
    assert client.get("/api/v1/admin/tenants", cookies=coster).status_code == 403


# --- QIK-521 worker monitoring --------------------------------------------------------------------

def test_monitoring_lists_every_worker_with_activity(client):
    _seed(client)
    body = client.get("/api/v1/admin/worker-monitoring", cookies=_admin(client)).json()
    rows = {row["id"]: row for row in body["items"]}

    assert body["total"] == 3
    assert rows["a1"]["calls"] == 3 and rows["a1"]["last_seen"] is not None
    assert rows["a2"]["calls"] == 0 and rows["a2"]["last_seen"] is None, "an idle worker is visible"
    assert rows["b1"]["enabled"] is False


def test_monitoring_puts_the_busiest_worker_first(client):
    _seed(client)
    body = client.get("/api/v1/admin/worker-monitoring", cookies=_admin(client)).json()
    assert [row["id"] for row in body["items"]][0] == "a1"


def test_cost_columns_need_view_ai_cost_even_here(client):
    """Otherwise this endpoint becomes a way around the /admin/ai-cost gate, which is exactly the
    mistake the user directory made with platform authority."""
    _seed(client)
    reader = _grant(client, "ops.only@invalid", [Capability.view_customers.value])
    body = client.get("/api/v1/admin/worker-monitoring", cookies=reader).json()
    assert body["cost_visible"] is False
    for row in body["items"]:
        assert "cost_nano_usd" not in row and "input_tokens" not in row
        assert "calls" in row, "activity is operational and stays visible"

    full = client.get("/api/v1/admin/worker-monitoring", cookies=_admin(client)).json()
    assert full["cost_visible"] is True
    assert any("cost_nano_usd" in row for row in full["items"])


def test_monitoring_filters_by_tenant(client):
    _seed(client)
    body = client.get("/api/v1/admin/worker-monitoring?tenant_id=beta",
                      cookies=_admin(client)).json()
    assert [row["id"] for row in body["items"]] == ["b1"]


@pytest.mark.parametrize("path", ["/api/v1/admin/ai-cost", "/api/v1/admin/worker-monitoring"])
def test_both_are_closed_to_outsiders(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, cookies=auth_cookies("acme", "owner")).status_code == 403


def test_a_super_admin_holds_the_new_capability_by_default():
    """Adding a capability must not silently remove access from existing super_admins."""
    from app.modules.identity.admin_rbac import AdminRole, default_capabilities

    assert Capability.view_ai_cost in default_capabilities(AdminRole.super_admin)
    assert Capability.view_ai_cost not in default_capabilities(AdminRole.viewer)
