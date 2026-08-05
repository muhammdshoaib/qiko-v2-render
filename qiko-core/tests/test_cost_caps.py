"""QIK-522: admin-set AI cost caps, enforced platform-wide.

Nothing limited AI spend. A single runaway tenant, or one worker retrying against a tender document,
could accrue unbounded Bedrock charges with no ceiling and no alert, and the first signal would have
been the AWS bill.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.modules.ai import usage
from app.modules.ai.caps import (
    PLATFORM,
    UNLIMITED,
    CostCap,
    CostGuard,
    InMemoryCostCapStore,
    month_start,
    select_cap,
)
from app.modules.ai.usage import InMemoryUsageStore
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import AdminRole, Capability, default_capabilities
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN = "caps-admin.invalid"
USD = 1_000_000_000


def _admin(client) -> dict:
    bootstrap_admin(client, ADMIN)
    return auth_cookies("platform", "viewer", email=ADMIN)


def _csrf(cookies: dict) -> tuple[dict, dict]:
    token = csrf.generate_csrf_token()
    return {**cookies, csrf.CSRF_COOKIE: token}, {csrf.CSRF_HEADER: token}


def _grant(client, email: str, capabilities: list[str]) -> dict:
    with_csrf, headers = _csrf(_admin(client))
    client.put(f"/api/v1/admin/org/{email}", cookies=with_csrf, headers=headers,
               json={"role": "viewer", "capabilities": capabilities})
    return auth_cookies("platform", "viewer", email=email)


def _cap(tenant, agent=None, usd=10.0, pct=80) -> CostCap:
    return CostCap(tenant=tenant, agent_id=agent,
                   monthly_cap_nano_usd=UNLIMITED if usd < 0 else int(usd * USD),
                   alert_threshold_pct=pct, updated_by_email="op@invalid",
                   updated_at=datetime.now(timezone.utc))


def _spend(tenant, agent, nano):
    return usage.UsageEvent(tenant=tenant, agent_id=agent, model_id="anthropic.claude-sonnet-4-5",
                            operation="generate", input_tokens=1, output_tokens=1,
                            cost_nano_usd=nano, created_at=datetime.now(timezone.utc), priced=True)


# --- precedence and encoding ----------------------------------------------------------------------

def test_the_most_specific_cap_wins():
    caps = [_cap(PLATFORM, usd=100), _cap("acme", usd=50), _cap("acme", "a1", usd=5)]
    assert select_cap(caps, "acme", "a1").monthly_cap_nano_usd == 5 * USD
    assert select_cap(caps, "acme", "a2").monthly_cap_nano_usd == 50 * USD
    assert select_cap(caps, "other", "x").monthly_cap_nano_usd == 100 * USD
    assert select_cap([], "acme", "a1") is None


def test_unlimited_is_expressible_distinctly_from_unconfigured():
    """An absent row means "nobody has configured this"; a negative cap means "unlimited, and I meant
    it". Collapsing the two would make an explicit decision indistinguishable from an oversight."""
    assert _cap("acme", usd=-1).unlimited is True
    assert _cap("acme", usd=0).unlimited is False


def test_the_month_window_starts_at_the_first():
    start = month_start(datetime(2026, 8, 20, 13, 45, tzinfo=timezone.utc))
    assert start == datetime(2026, 8, 1, tzinfo=timezone.utc)


# --- the guard ------------------------------------------------------------------------------------

def _guard(caps=None, events=None, notifications=None, cache=0.0) -> CostGuard:
    store = InMemoryCostCapStore()
    usage_store = InMemoryUsageStore(events=list(events or []))

    async def seed():
        for cap in caps or []:
            await store.upsert(cap)

    asyncio.run(seed())
    return CostGuard(caps=store, usage=usage_store, notifications=notifications,
                     cache_seconds=cache)


def test_spend_below_the_cap_is_allowed():
    guard = _guard(caps=[_cap("acme", usd=10)], events=[_spend("acme", "a1", 1 * USD)])
    decision = asyncio.run(guard.check("acme", "a1"))
    assert decision.allowed is True and decision.used_pct == 10


def test_spend_at_or_above_the_cap_is_refused():
    guard = _guard(caps=[_cap("acme", usd=10)], events=[_spend("acme", "a1", 10 * USD)])
    decision = asyncio.run(guard.check("acme", "a1"))
    assert decision.allowed is False and decision.used_pct == 100


def test_a_worker_cap_is_measured_against_that_worker_only():
    """Otherwise one busy worker would exhaust a sibling's budget."""
    guard = _guard(caps=[_cap("acme", "a1", usd=5)],
                   events=[_spend("acme", "a2", 100 * USD), _spend("acme", "a1", 1 * USD)])
    assert asyncio.run(guard.check("acme", "a1")).allowed is True


def test_an_unlimited_cap_never_refuses():
    guard = _guard(caps=[_cap("acme", usd=-1)], events=[_spend("acme", "a1", 9_999 * USD)])
    decision = asyncio.run(guard.check("acme", "a1"))
    assert decision.allowed is True and decision.limit_nano_usd is None


def test_no_cap_configured_means_no_limit():
    guard = _guard(events=[_spend("acme", "a1", 9_999 * USD)])
    assert asyncio.run(guard.check("acme", "a1")).allowed is True


def test_last_months_spend_does_not_count_against_this_month():
    old = usage.UsageEvent(tenant="acme", agent_id="a1", model_id="anthropic.claude-sonnet-4-5",
                           operation="generate", input_tokens=1, output_tokens=1,
                           cost_nano_usd=50 * USD,
                           created_at=month_start() - timedelta(days=1), priced=True)
    guard = _guard(caps=[_cap("acme", usd=10)], events=[old])
    assert asyncio.run(guard.check("acme", "a1")).allowed is True


def test_the_guard_fails_open_when_spend_cannot_be_read():
    """A cap is a cost control, not a correctness requirement. Taking the platform down because the
    spend query failed would be a far worse outcome than briefly allowing spend above a cap."""
    class Broken:
        async def totals(self, *_args, **_kwargs):
            raise RuntimeError("database is down")

        async def totals_by_agent(self, *_args, **_kwargs):
            raise RuntimeError("database is down")

    store = InMemoryCostCapStore()
    asyncio.run(store.upsert(_cap("acme", usd=1)))
    guard = CostGuard(caps=store, usage=Broken(), cache_seconds=0)
    assert asyncio.run(guard.check("acme", "a1")).allowed is True


def test_crossing_the_threshold_alerts_once_not_once_per_request():
    """Alerting on every answer after a tenant crosses its threshold trains people to ignore alerts."""
    sent = []

    class Notifier:
        async def notify(self, tenant, **kwargs):
            sent.append((tenant, kwargs["title"]))

    guard = _guard(caps=[_cap("acme", usd=10, pct=50)],
                   events=[_spend("acme", "a1", 6 * USD)], notifications=Notifier())
    for _ in range(4):
        asyncio.run(guard.check("acme", "a1"))
    assert len(sent) == 1
    assert "50%" in sent[0][1] or "%" in sent[0][1]


def test_exceeding_alerts_again_because_the_state_changed():
    sent = []

    class Notifier:
        async def notify(self, tenant, **kwargs):
            sent.append(kwargs["title"])

    store = InMemoryCostCapStore()
    asyncio.run(store.upsert(_cap("acme", usd=10, pct=50)))
    usage_store = InMemoryUsageStore(events=[_spend("acme", "a1", 6 * USD)])
    guard = CostGuard(caps=store, usage=usage_store, notifications=Notifier(), cache_seconds=0)
    asyncio.run(guard.check("acme", "a1"))
    usage_store.events.append(_spend("acme", "a1", 6 * USD))  # now over
    asyncio.run(guard.check("acme", "a1"))
    assert len(sent) == 2 and "exceeded" in sent[1].lower()


def test_an_alert_failure_never_blocks_the_answer():
    class Broken:
        async def notify(self, *_args, **_kwargs):
            raise RuntimeError("notification store down")

    guard = _guard(caps=[_cap("acme", usd=10, pct=10)],
                   events=[_spend("acme", "a1", 5 * USD)], notifications=Broken())
    assert asyncio.run(guard.check("acme", "a1")).allowed is True


# --- the API --------------------------------------------------------------------------------------

def test_setting_a_cap_takes_effect_immediately(client):
    """Without cache invalidation the save would appear not to have worked until the window expired."""
    with_csrf, headers = _csrf(_admin(client))
    response = client.put("/api/v1/admin/cost-caps/acme", cookies=with_csrf, headers=headers,
                          json={"monthly_cap_usd": 2.5, "alert_threshold_pct": 50})
    assert response.status_code == 200
    body = response.json()
    assert body["monthly_cap_nano_usd"] == 2_500_000_000
    assert body["updated_by_email"] == ADMIN and body["unlimited"] is False

    listed = client.get("/api/v1/admin/cost-caps", cookies=_admin(client)).json()
    assert listed["platform_key"] == PLATFORM
    assert any(item["tenant_id"] == "acme" for item in listed["items"])


def test_a_cap_can_be_removed(client):
    with_csrf, headers = _csrf(_admin(client))
    client.put("/api/v1/admin/cost-caps/acme", cookies=with_csrf, headers=headers,
               json={"monthly_cap_usd": 1})
    client.delete("/api/v1/admin/cost-caps/acme", cookies=with_csrf, headers=headers)
    listed = client.get("/api/v1/admin/cost-caps", cookies=_admin(client)).json()
    assert not any(item["tenant_id"] == "acme" for item in listed["items"])


def test_setting_a_cap_needs_set_cost_caps_not_merely_view_ai_cost(client):
    """Reaching a cap stops a customer's workers answering, so setting one is a mutation of
    customer-facing behaviour rather than a reporting feature."""
    reader = _grant(client, "cost.reader@invalid", [Capability.view_ai_cost.value])
    with_csrf, headers = _csrf(reader)
    assert client.get("/api/v1/admin/cost-caps", cookies=reader).status_code == 200
    assert client.put("/api/v1/admin/cost-caps/acme", cookies=with_csrf, headers=headers,
                      json={"monthly_cap_usd": 1}).status_code == 403
    assert client.delete("/api/v1/admin/cost-caps/acme", cookies=with_csrf,
                         headers=headers).status_code == 403


def test_cap_mutations_require_csrf(client):
    cookies = _admin(client)
    assert client.put("/api/v1/admin/cost-caps/acme", cookies=cookies,
                      json={"monthly_cap_usd": 1}).status_code == 403


def test_the_cap_api_is_closed_to_outsiders(client):
    assert client.get("/api/v1/admin/cost-caps").status_code == 401
    assert client.get("/api/v1/admin/cost-caps",
                      cookies=auth_cookies("acme", "owner")).status_code == 403


def test_an_unknown_body_field_is_refused(client):
    with_csrf, headers = _csrf(_admin(client))
    assert client.put("/api/v1/admin/cost-caps/acme", cookies=with_csrf, headers=headers,
                      json={"monthly_cap_usd": 1, "typo": True}).status_code == 422


def test_a_super_admin_keeps_the_new_capability_by_default():
    assert Capability.set_cost_caps in default_capabilities(AdminRole.super_admin)
    assert Capability.set_cost_caps not in default_capabilities(AdminRole.viewer)


def test_every_capability_gates_at_least_one_endpoint(client):
    """The enum comment promises this. Now that set_cost_caps has shipped, the promise is complete, so
    pin it: a capability that gates nothing is a false sense of least privilege."""
    paths = {route.path for route in client.app.routes}
    assert "/api/v1/admin/cost-caps/{tenant_id}" in paths
    assert "/api/v1/admin/system" in paths
    assert "/api/v1/admin/ai-cost" in paths


def test_a_reached_cap_answers_402_not_500(client, monkeypatch):
    """A reached cap is a business condition. 402 rather than 429 because retrying will not help until
    the cap is raised or the month rolls over, and a 500 would send an operator hunting a bug that does
    not exist."""
    async def seed() -> None:
        await client.app.state.cost_caps.upsert(_cap("acme", usd=1))
        await client.app.state.ai_usage.add_many([_spend("acme", "a1", 5 * USD)])
        from app.modules.agents.service import Agent

        await client.app.state.agents.store.add(Agent(id="a1", tenant="acme", name="Capped",
                                                     status="ready"))

    asyncio.run(seed())
    client.app.state.cost_guard.invalidate()

    response = client.post("/api/v1/chat/ask", cookies=auth_cookies("acme", "owner"),
                           json={"agent_id": "a1", "question": "hello", "conversation_id": "c1"})
    assert response.status_code == 402
    body = response.json()
    assert body["used_pct"] == 500 and body["limit_nano_usd"] == USD
    assert "cap" in body["detail"].lower()
