"""Generic in-app notification module + Sales-Intelligence trigger wiring.

Covers the store protocol (in-memory + Postgres-backed on aiosqlite), the tenant/recipient
scoping (BOLA-safe), the HTTP inbox endpoints, and each of the 5 SI notification triggers from the
non-AI components matrix (review-required, SF sync success/failed, scan-failed, deadline-reminder)
plus reviewer-assigned.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlNotificationStore
from app.modules.notifications.models import CATEGORY_SALES_INTELLIGENCE, Notification
from app.modules.notifications.service import NotificationService
from app.modules.sales_intelligence.models import Opportunity
from app.modules.sales_intelligence.notifications import SalesNotificationService
from app.modules.sales_intelligence.salesforce import SalesforceAuthService, SalesforcePushService
from app.modules.sales_intelligence.service import OpportunityMutationService, OpportunityService

from tests.helpers import auth_cookies


# --- generic service (in-memory) ---
async def test_notification_service_notify_list_and_read():
    svc = NotificationService()
    n = await svc.notify("acme", "review_required", "Review required", "Body", user_id="u1")
    assert n.is_read() is False
    items = await svc.list("acme", "u1")
    assert len(items) == 1
    assert await svc.unread_count("acme", "u1") == 1
    await svc.mark_read("acme", n.id, "u1")
    assert await svc.unread_count("acme", "u1") == 0


async def test_notification_tenant_wide_visible_to_all_users_in_tenant():
    svc = NotificationService()
    await svc.notify("acme", "scan_failed", "Scan Failed", user_id=None)  # tenant-wide
    await svc.notify("acme", "review_required", "For u1", user_id="u1")  # addressed
    # u2 sees only the tenant-wide row, not u1's addressed row
    u2_items = await svc.list("acme", "u2")
    assert [n.title for n in u2_items] == ["Scan Failed"]
    # u1 sees both
    assert len(await svc.list("acme", "u1")) == 2


async def test_notification_is_tenant_isolated():
    svc = NotificationService()
    await svc.notify("acme", "review_required", "Acme", user_id="u1")
    assert await svc.list("beta", "u1") == []
    assert await svc.unread_count("beta", "u1") == 0


async def test_mark_all_read_scoped_by_category():
    svc = NotificationService()
    await svc.notify("acme", "review_required", "SI", category=CATEGORY_SALES_INTELLIGENCE, user_id="u1")
    await svc.notify("acme", "other", "Gen", user_id="u1")
    updated = await svc.mark_all_read("acme", "u1", category=CATEGORY_SALES_INTELLIGENCE)
    assert updated == 1
    assert await svc.unread_count("acme", "u1") == 1  # the general one is still unread


# --- Sql-backed store (aiosqlite) ---
async def _sessionmaker(path: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def test_sql_notification_store_persists_and_is_tenant_scoped(tmp_path):
    sm, engine = await _sessionmaker(str(tmp_path / "n.db"))
    store = SqlNotificationStore(sm)
    n = await store.add(Notification(id="n1", tenant="acme", type="review_required", title="R", user_id="u1"))
    await engine.dispose()  # simulate restart

    sm2, _ = await _sessionmaker(str(tmp_path / "n.db"))
    store2 = SqlNotificationStore(sm2)
    assert (await store2.get("acme", "n1")).title == "R"
    assert await store2.get("beta", "n1") is None  # tenant-scoped
    assert len(await store2.list_for_user("acme", "u1")) == 1
    assert await store2.list_for_user("beta", "u1") == []
    marked = await store2.mark_read("acme", "n1", "u1")
    assert marked.is_read()
    assert await store2.unread_count("acme", "u1") == 0
    _ = n


# --- SI triggers ---
async def test_review_required_trigger_on_manual_create():
    notifications = NotificationService()
    notifier = SalesNotificationService(notifications=notifications)
    mutation = OpportunityMutationService(notifier=notifier)
    await mutation.create_manual("acme", "ag1", {"title": "Tender"}, actor_user_id="u1")
    items = await notifications.list("acme", None, category=CATEGORY_SALES_INTELLIGENCE)
    assert any(n.type == "review_required" for n in items)


async def test_scan_failed_trigger(monkeypatch):
    notifications = NotificationService()
    notifier = SalesNotificationService(notifications=notifications)
    svc = OpportunityService(notifier=notifier)
    source = await svc.ensure_ungm_source("acme", "ag1")
    source.status = "active"
    await svc.sources.update(source)

    def boom(_filters):
        raise RuntimeError("ungm down")

    monkeypatch.setattr(svc.ungm, "search", boom)
    with pytest.raises(RuntimeError):
        await svc.scan_ungm("acme", "ag1", {})
    items = await notifications.list("acme", None, category=CATEGORY_SALES_INTELLIGENCE)
    assert any(n.type == "scan_failed" for n in items)


async def test_reviewer_assigned_trigger_and_activity_log():
    notifications = NotificationService()
    notifier = SalesNotificationService(notifications=notifications)
    mutation = OpportunityMutationService(notifier=notifier)
    opp = await mutation.create_manual("acme", "ag1", {"title": "Tender"}, actor_user_id="u1")
    opp = await mutation.assign_reviewer(opp, "u2", "Alice", actor_user_id="u1")
    assert opp.assigned_reviewer_user_id == "u2"
    assert opp.assigned_reviewer_name == "Alice"
    assert opp.assigned_at is not None
    # reviewer gets the addressed notification
    assert any(n.type == "reviewer_assigned" for n in await notifications.list("acme", "u2"))
    # audit trail: an assign activity log exists
    logs = await mutation.activity_logs.list_for_agent("acme", "ag1", action="opportunity_reviewer_assigned")
    assert len(logs) == 1 and logs[0].actor_user_id == "u1"


async def test_assign_reviewer_clear_resets_fields():
    mutation = OpportunityMutationService()
    opp = await mutation.create_manual("acme", "ag1", {"title": "T"}, actor_user_id="u1")
    opp = await mutation.assign_reviewer(opp, "u2", "Alice", actor_user_id="u1")
    opp = await mutation.assign_reviewer(opp, None, None, actor_user_id="u1")
    assert opp.assigned_reviewer_user_id is None
    assert opp.assigned_at is None
    logs = await mutation.activity_logs.list_for_agent("acme", "ag1", action="opportunity_reviewer_unassigned")
    assert len(logs) == 1


async def test_salesforce_sync_success_and_failed_triggers():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at", "instance_url": "https://x.my.salesforce.com",
                                              "token_type": "Bearer", "id": "https://login/id/00Dorg/005user"})
        return httpx.Response(201, json={"id": "006SF1", "success": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifications = NotificationService()
    notifier = SalesNotificationService(notifications=notifications)
    auth = SalesforceAuthService()
    conn = await auth.get_or_create_connection("acme", "ag1")
    conn.status = "connected"
    conn.instance_url = "https://x.my.salesforce.com"
    from app.core.crypto import encrypt
    conn.access_token = encrypt("at")
    from datetime import datetime, timedelta, timezone
    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await auth.connections.update(conn)

    push = SalesforcePushService(auth=auth, client=client, notifier=notifier)
    opp = Opportunity(id="o1", tenant="acme", agent_id="ag1", external_id="e1", source_key="ted",
                      source_name="TED", title="Tender", stage="validated")
    await push.push(opp)
    assert any(n.type == "sf_sync_success" for n in await notifications.list("acme", None))

    # now force a failure on create
    def fail_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "at", "instance_url": "https://x.my.salesforce.com"})
        return httpx.Response(400, json=[{"message": "bad", "errorCode": "E"}])

    push2 = SalesforcePushService(auth=auth, client=httpx.Client(transport=httpx.MockTransport(fail_handler)),
                                  notifier=notifier)
    opp2 = Opportunity(id="o2", tenant="acme", agent_id="ag1", external_id="e2", source_key="ted",
                       source_name="TED", title="Tender2", stage="validated")
    with pytest.raises(Exception):
        await push2.push(opp2)
    assert any(n.type == "sf_sync_failed" for n in await notifications.list("acme", None))


async def test_deadline_reminder_trigger():
    notifications = NotificationService()
    notifier = SalesNotificationService(notifications=notifications)
    svc = OpportunityService(notifier=notifier)
    opp = Opportunity(id="o1", tenant="acme", agent_id="ag1", external_id="e1", source_key="ted",
                      source_name="TED", title="Tender", stage="validated", assigned_reviewer_user_id="u2")
    await svc.send_deadline_reminder(opp, 2)
    items = await notifications.list("acme", "u2")
    assert any(n.type == "deadline_reminder" and "2 days" in n.body for n in items)


# --- HTTP endpoints ---
def test_assign_reviewer_and_decisions_endpoints(client):
    cookies = auth_cookies(tenant="acme")
    created = client.post("/api/v1/sales-intelligence/agent-rev-1/opportunities", cookies=cookies,
                          json={"title": "Static security guarding", "country": "Kenya", "buyer": "UN"})
    opp_id = created.json()["opportunity"]["id"]

    assigned = client.patch(f"/api/v1/sales-intelligence/agent-rev-1/opportunities/{opp_id}/assign-reviewer",
                            cookies=cookies, json={"user_id": "u-99", "name": "Alice"})
    assert assigned.status_code == 200
    body = assigned.json()["opportunity"]
    assert body["assignedReviewerUserId"] == "u-99"
    assert body["assignedReviewerName"] == "Alice"
    assert body["assignedAt"] is not None

    # a review decision, then the decisions endpoint should list it
    client.post(f"/api/v1/sales-intelligence/agent-rev-1/opportunities/{opp_id}/review", cookies=cookies,
                json={"decision": "approved", "notes": "ok"})
    decisions = client.get(f"/api/v1/sales-intelligence/agent-rev-1/opportunities/{opp_id}/decisions", cookies=cookies)
    assert decisions.status_code == 200
    rows = decisions.json()["decisions"]
    assert len(rows) == 1
    assert rows[0]["decision"] == "approved" and rows[0]["decisionLabel"] == "Approved"


def test_assign_reviewer_requires_editor_role(client):
    viewer = auth_cookies(tenant="acme", role="viewer")
    resp = client.patch("/api/v1/sales-intelligence/agent-rev-2/opportunities/x/assign-reviewer",
                        cookies=viewer, json={"user_id": "u1"})
    assert resp.status_code == 403


def test_notifications_inbox_endpoints_and_tenant_isolation(client):
    cookies = auth_cookies(tenant="acme", user_id="u-a")
    # trigger a review-required notification by creating an opportunity that needs review
    client.post("/api/v1/sales-intelligence/agent-notif-1/opportunities", cookies=cookies,
                json={"title": "Security guarding services", "country": "Kenya", "buyer": "UN"})

    listing = client.get("/api/v1/notifications", cookies=cookies)
    assert listing.status_code == 200
    data = listing.json()
    assert data["unreadCount"] >= 1
    assert len(data["notifications"]) >= 1
    nid = data["notifications"][0]["id"]

    # another tenant cannot see acme's notifications
    other = client.get("/api/v1/notifications", cookies=auth_cookies(tenant="beta", user_id="u-b"))
    assert other.json()["notifications"] == []

    read = client.post(f"/api/v1/notifications/{nid}/read", cookies=cookies)
    assert read.status_code == 200 and read.json()["notification"]["read"] is True

    read_all = client.post("/api/v1/notifications/read-all", cookies=cookies)
    assert read_all.status_code == 200
    assert client.get("/api/v1/notifications/unread-count", cookies=cookies).json()["unreadCount"] == 0


def test_notifications_require_authentication(client):
    assert client.get("/api/v1/notifications").status_code == 401
