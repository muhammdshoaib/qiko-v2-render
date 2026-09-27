"""QIKO-1073: read-only platform-admin support view of an intelligence worker's chat and
discrepancies, without provisioning the admin as a tenant `users` row."""
import asyncio

from app.modules.agents.service import Agent
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import Capability
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN = "support-admin.invalid"


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


def _seed(client) -> None:
    async def seed() -> None:
        await client.app.state.agents.store.add(Agent(
            id="qiw-1", tenant="acme", name="QIW", atype="intelligence", status="ready"))
        await client.app.state.agents.store.add(Agent(
            id="fin-1", tenant="acme", name="Finance", atype="finance", status="ready"))
        # A second intelligence worker in the SAME tenant, so a regression test can prove the
        # qiw-1 conversation-history endpoint refuses a conversation id that belongs to qiw-2, even
        # though ChatService.history() itself only checks the tenant, not the agent.
        await client.app.state.agents.store.add(Agent(
            id="qiw-2", tenant="acme", name="QIW2", atype="intelligence", status="ready"))
        await client.app.state.chat.store.ensure(
            "acme", "c1", user_id="u1", agent_id="qiw-1")
        await client.app.state.chat.store.append("acme", "c1", "user", "what is left before launch?")
        await client.app.state.chat.store.append("acme", "c1", "assistant", "three open items.")
        await client.app.state.chat.store.ensure(
            "acme", "c2", user_id="u2", agent_id="qiw-2")
        await client.app.state.chat.store.append("acme", "c2", "user", "qiw-2's own question")

    asyncio.run(seed())


def test_support_view_needs_the_capability(client):
    _seed(client)
    reader = _grant(client, "ro.support@invalid", [Capability.view_customers.value])
    assert client.get("/api/v1/admin/support/workers/qiw-1",
                      cookies=reader).status_code == 403
    granted = _grant(client, "granted.support@invalid", [Capability.support_view_worker.value])
    assert client.get("/api/v1/admin/support/workers/qiw-1",
                      cookies=granted).status_code == 200


def test_support_view_404s_for_a_non_intelligence_worker(client):
    _seed(client)
    granted = _grant(client, "granted2.support@invalid", [Capability.support_view_worker.value])
    assert client.get("/api/v1/admin/support/workers/fin-1",
                      cookies=granted).status_code == 404
    assert client.get("/api/v1/admin/support/workers/does-not-exist",
                      cookies=granted).status_code == 404


def test_support_view_returns_conversations_and_history_for_the_agents_own_tenant(client):
    _seed(client)
    granted = _grant(client, "granted3.support@invalid", [Capability.support_view_worker.value])

    summary = client.get("/api/v1/admin/support/workers/qiw-1", cookies=granted).json()
    assert summary == {"id": "qiw-1", "tenant_id": "acme", "name": "QIW", "atype": "intelligence"}

    conversations = client.get(
        "/api/v1/admin/support/workers/qiw-1/conversations", cookies=granted).json()
    assert [c["id"] for c in conversations] == ["c1"]

    history = client.get(
        "/api/v1/admin/support/workers/qiw-1/conversations/c1", cookies=granted).json()
    assert [m["text"] for m in history] == ["what is left before launch?", "three open items."]


def test_support_view_404s_for_a_conversation_that_belongs_to_a_different_worker(client):
    _seed(client)
    granted = _grant(client, "granted5.support@invalid", [Capability.support_view_worker.value])

    # c2 exists, and is in the same tenant ("acme") as qiw-1 - but it belongs to qiw-2, not qiw-1.
    # ChatService.history(tenant, conversation_id) alone cannot tell the difference, so the router
    # must reject it itself rather than leaking a different worker's conversation content.
    assert client.get(
        "/api/v1/admin/support/workers/qiw-1/conversations/c2", cookies=granted).status_code == 404

    # Sanity: c2 is real and reads fine through its OWN worker's endpoint, so the 404 above is the
    # ownership check doing its job, not c2 being unreadable in general.
    own = client.get(
        "/api/v1/admin/support/workers/qiw-2/conversations/c2", cookies=granted)
    assert own.status_code == 200
    assert [m["text"] for m in own.json()] == ["qiw-2's own question"]


def test_support_view_writes_one_audit_row_without_content(client):
    _seed(client)
    granted = _grant(client, "granted4.support@invalid", [Capability.support_view_worker.value])
    client.get("/api/v1/admin/support/workers/qiw-1/conversations", cookies=granted)

    rows = asyncio.run(client.app.state.audit.list(action="access.support_worker_viewed"))
    assert len(rows) == 1
    row = rows[0]
    assert row["tenant_id"] == "acme"
    assert row["target_id"] == "qiw-1"
    assert row["actor_type"] == "platform_admin"
    assert row["metadata"] == {"view": "conversations"}


def _seed_discrepancy(client, *, ref: str = "QIW-1004", suffix: str = "1") -> None:
    from datetime import datetime, timedelta, timezone

    from app.modules.intelligence.models import Signal

    # Occurred times are relative to "now" rather than a fixed calendar date: the route (matching
    # the tenant-facing route exactly) calls analyze_paginated() with no since=/now=, so it defaults
    # to a 30-day lookback from the real wall clock. A hardcoded past date silently falls outside
    # that window once enough real time has passed (the same class of flake fixed for two other
    # discrepancy tests in QIKO-1071 / commit 01d939b, which pinned an explicit now= instead).
    now = datetime.now(timezone.utc)

    async def seed() -> None:
        await client.app.state.intelligence_signal_store.add(Signal(
            tenant="acme", agent_id="qiw-1", source="slack", kind="message",
            external_id=f"s{suffix}", container="T1/C1", actor="dev", ref=ref,
            title="pricing is done", body="pricing is done", url=None,
            occurred_at=now - timedelta(days=1),
            tags=[], flagged=False))
        await client.app.state.intelligence_signal_store.add(Signal(
            tenant="acme", agent_id="qiw-1", source="qiko_track", kind="ticket_moved",
            external_id=f"qt{suffix}", container="QIW", actor="qiko_track", ref=ref,
            title=ref, body="", url=None,
            occurred_at=now - timedelta(days=1) + timedelta(minutes=5),
            tags=[], flagged=False, meta={"state": {"status": "IN_PROGRESS"}}))

    asyncio.run(seed())


def test_support_view_discrepancies_matches_the_tenant_facing_engine(client):
    _seed(client)
    _seed_discrepancy(client)
    granted = _grant(client, "granted5.support@invalid", [Capability.support_view_worker.value])

    body = client.get(
        "/api/v1/admin/support/workers/qiw-1/discrepancies", cookies=granted).json()
    assert body["total"] == 1
    assert body["items"][0]["class"] == "claimed_not_done"
    assert body["items"][0]["ref"] == "QIW-1004"


def test_support_view_discrepancies_paginates_with_total_and_validates_bounds(client):
    _seed(client)
    _seed_discrepancy(client)
    _seed_discrepancy(client, ref="QIW-1005", suffix="2")
    granted = _grant(client, "paged.support@invalid", [Capability.support_view_worker.value])
    url = "/api/v1/admin/support/workers/qiw-1/discrepancies"

    first = client.get(url, params={"limit": 1, "offset": 0}, cookies=granted)
    second = client.get(url, params={"limit": 1, "offset": 1}, cookies=granted)
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 2
    assert len(first.json()["items"]) == len(second.json()["items"]) == 1
    assert first.json()["items"][0]["ref"] != second.json()["items"][0]["ref"]

    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        assert client.get(url, params=params, cookies=granted).status_code == 422

    rows = asyncio.run(client.app.state.audit.list(action="access.support_worker_viewed"))
    assert len(rows) == 2
    assert all(row["tenant_id"] == "acme" and row["target_id"] == "qiw-1"
               and row["metadata"] == {"view": "discrepancies"} for row in rows)
