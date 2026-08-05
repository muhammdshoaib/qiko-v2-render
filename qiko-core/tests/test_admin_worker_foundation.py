import asyncio
import json
import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Tenant as TenantRow
from app.db.sync_stores import SqlCustomerDirectory, SqlSubscriptionStore
from app.modules.admin import router as admin_router
from app.modules.admin.customers import CustomerRecord
from app.modules.agents import router as agents_router
from app.modules.agents.service import Agent, AgentService, InMemoryAgentStore, PlanLimitError
from app.modules.billing.plans import get_plan
from app.modules.billing.subscriptions import Subscription
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import AdminRole
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN_EMAIL = "worker-admin.invalid"
VIEWER_EMAIL = "worker-viewer.invalid"


def _super_admin(client) -> dict:
    bootstrap_admin(client, ADMIN_EMAIL)
    return auth_cookies("platform", "viewer", email=ADMIN_EMAIL)


def _platform_viewer(client) -> dict:
    async def seed() -> None:
        await client.app.state.admin_org.bootstrap_super_admin(ADMIN_EMAIL)
        token = await client.app.state.admin_org.invite(ADMIN_EMAIL, VIEWER_EMAIL, AdminRole.viewer)
        await client.app.state.admin_org.accept(token)

    asyncio.run(seed())
    return auth_cookies("platform", "viewer", email=VIEWER_EMAIL)


def _csrf(cookies: dict) -> tuple[dict, dict]:
    token = csrf.generate_csrf_token()
    return {**cookies, csrf.CSRF_COOKIE: token}, {csrf.CSRF_HEADER: token}


def _seed_customer_and_workers(client) -> None:
    client.app.state.customers.add(CustomerRecord("acme", "owner-acme.invalid", "pro"))
    client.app.state.customers.add(CustomerRecord("beta", "owner-beta.invalid", "free"))

    async def seed() -> None:
        await client.app.state.agents.store.add(Agent(
            id="a1", tenant="acme", name="Visible", config={
                "expertise": "Tender writing",
                "system_prompt": "must-not-leak",
                "nested": {"apiToken": "must-not-leak"},
            }
        ))
        await client.app.state.agents.store.add(Agent(
            id="a2", tenant="acme", name="Disabled", enabled=False
        ))
        await client.app.state.agents.store.add(Agent(
            id="a3", tenant="acme", name="Archived", config={"archived": True}
        ))
        await client.app.state.agents.store.add(Agent(
            id="b1", tenant="beta", name="Other tenant"
        ))

    asyncio.run(seed())


def test_super_admin_cannot_be_removed(client):
    actor = "actor-admin@invalid"
    target = "target-admin@invalid"
    bootstrap_admin(client, actor)
    bootstrap_admin(client, target)
    cookies, headers = _csrf(auth_cookies("acme", "viewer", email=actor))
    assert client.delete(f"/api/v1/admin/org/{target}", cookies=cookies, headers=headers).status_code == 409


def test_platform_admin_requires_mfa_session(client):
    email = "mfa-admin@invalid"
    bootstrap_admin(client, email)
    cookies = auth_cookies("acme", "viewer", email=email, mfa=False)
    assert client.get("/api/v1/admin/me", cookies=cookies).status_code == 403


def test_admin_detail_viewer_reads_all_workers_with_safe_config_and_role(client):
    _seed_customer_and_workers(client)
    viewer = _platform_viewer(client)

    me = client.get("/api/v1/admin/me", cookies=viewer)
    detail = client.get("/api/v1/admin/customers/acme", cookies=viewer)

    assert me.status_code == 200
    # /admin/me now also reports the effective capability set so the UI can hide what the caller
    # cannot do. A viewer's default is read-only.
    assert me.json() == {"role": "viewer", "capabilities": ["view_customers"]}
    assert detail.status_code == 200
    assert {worker["id"] for worker in detail.json()["workers"]} == {"a1", "a2", "a3"}
    assert detail.json()["workers"][0]["config"] == {"expertise": "Tender writing"}
    assert detail.json()["worker_state_audit"] == []


def test_worker_toggle_requires_super_admin_csrf_and_exact_customer_ownership(client):
    _seed_customer_and_workers(client)
    viewer = _platform_viewer(client)
    admin = _super_admin(client)
    admin_with_csrf, headers = _csrf(admin)
    path = "/api/v1/admin/customers/acme/workers/a1/enabled"

    assert client.patch(path, json={"enabled": False}, cookies=viewer).status_code == 403
    assert client.post(
        "/api/v1/admin/customers/acme/studio", json={"enabled": True}, cookies=viewer
    ).status_code == 403
    assert client.delete("/api/v1/admin/customers/acme", cookies=viewer).status_code == 403
    assert client.patch(path, json={"enabled": False}, cookies=admin).status_code == 403
    assert client.patch(
        path, json={"enabled": False}, cookies=admin_with_csrf,
        headers={csrf.CSRF_HEADER: "mismatch"},
    ).status_code == 403
    changed = client.patch(
        path, json={"enabled": False, "reason": "contract ended"},
        cookies=admin_with_csrf, headers=headers,
    )
    repeated = client.patch(
        path, json={"enabled": False, "reason": "duplicate"},
        cookies=admin_with_csrf, headers=headers,
    )
    cross_tenant = client.patch(
        "/api/v1/admin/customers/acme/workers/b1/enabled",
        json={"enabled": False}, cookies=admin_with_csrf, headers=headers,
    )
    missing_worker = client.patch(
        "/api/v1/admin/customers/acme/workers/missing/enabled",
        json={"enabled": False}, cookies=admin_with_csrf, headers=headers,
    )

    assert changed.status_code == 200 and changed.json()["enabled"] is False
    assert repeated.status_code == 200
    assert cross_tenant.status_code == 404
    assert missing_worker.status_code == 404
    assert client.post(
        "/api/v1/admin/customers/acme/studio", json={"enabled": True}, cookies=admin
    ).status_code == 403
    assert client.delete("/api/v1/admin/customers/acme", cookies=admin).status_code == 403
    assert client.post(
        "/api/v1/admin/customers/acme/studio", json={"enabled": True},
        cookies=admin_with_csrf, headers={csrf.CSRF_HEADER: "mismatch"},
    ).status_code == 403
    assert client.delete(
        "/api/v1/admin/customers/acme", cookies=admin_with_csrf,
        headers={csrf.CSRF_HEADER: "mismatch"},
    ).status_code == 403
    assert client.post(
        "/api/v1/admin/customers/acme/studio", json={"enabled": True},
        cookies=admin_with_csrf, headers=headers,
    ).status_code == 200
    assert client.delete(
        "/api/v1/admin/customers/beta", cookies=admin_with_csrf, headers=headers,
    ).status_code == 200
    detail = client.get("/api/v1/admin/customers/acme", cookies=admin)
    assert len(detail.json()["worker_state_audit"]) == 1


def test_creator_hides_disabled_but_usage_counts_every_worker(client):
    _seed_customer_and_workers(client)
    client.app.state.subscriptions.activate("acme", "pro")
    cookies = auth_cookies("acme", "owner")

    visible = client.get("/api/v1/agents", cookies=cookies)
    usage = client.get("/api/v1/agents/usage", cookies=cookies)

    assert visible.status_code == 200
    assert [worker["id"] for worker in visible.json()] == ["a1"]
    assert usage.status_code == 200
    assert usage.json() == {"used_count": 3, "worker_limit": 3}


def test_sync_admin_mutations_are_offloaded(client, monkeypatch):
    _seed_customer_and_workers(client)
    admin, headers = _csrf(_super_admin(client))
    calls = []

    async def tracked(function, *args):
        calls.append(function.__name__)
        return function(*args)

    monkeypatch.setattr(admin_router, "run_in_threadpool", tracked)
    assert client.post(
        "/api/v1/admin/customers/acme/studio", json={"enabled": True},
        cookies=admin, headers=headers,
    ).status_code == 200
    assert client.delete(
        "/api/v1/admin/customers/beta", cookies=admin, headers=headers,
    ).status_code == 200
    assert "set_studio" in calls
    assert "soft_delete" in calls


def test_subscription_reads_are_offloaded(client, monkeypatch):
    calls = []

    async def tracked(function, *args):
        calls.append(function.__name__)
        return function(*args)

    monkeypatch.setattr(agents_router, "run_in_threadpool", tracked, raising=False)
    response = client.get("/api/v1/agents/usage", cookies=auth_cookies("acme", "owner"))
    assert response.status_code == 200
    assert "status" in calls


async def test_agent_service_uses_atomic_store_limit_and_counts_disabled(monkeypatch):
    service = AgentService()
    calls = 0
    original = InMemoryAgentStore.add_with_limit

    async def record(store, agent, worker_limit):
        nonlocal calls
        calls += 1
        return await original(store, agent, worker_limit)

    monkeypatch.setattr(InMemoryAgentStore, "add_with_limit", record)
    plan = get_plan("free")
    await service.create("acme", "First", plan)
    await service.set_enabled(
        "acme", (await service.list("acme"))[0].id, False,
        changed_by_email="admin.invalid",
    )
    with pytest.raises(PlanLimitError):
        await service.create("acme", "Second", plan)
    assert calls == 2


def test_migration_is_single_head_with_enabled_backfill_and_audit_indexes():
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0034_ai_usage_nano_usd"]

    migration = root / "alembic/versions/0025_agent_enabled_audit.py"
    source = migration.read_text()
    assert 'down_revision = "0024_billing_durability"' in source
    assert 'UPDATE agents SET enabled = true WHERE enabled IS NULL' in source
    assert 'server_default=sa.true()' in source
    assert 'ix_agent_state_audit_tenant_agent_created' in source


def test_migration_upgrades_legacy_agent_and_creates_indexes(tmp_path):
    database = tmp_path / "migration.db"
    os.environ["ALEMBIC_URL"] = f"sqlite:///{database}"
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "0024_billing_durability")
        connection = sqlite3.connect(database)
        connection.execute("INSERT INTO tenants (id, name, created_at) VALUES ('acme', 'Acme', CURRENT_TIMESTAMP)")
        connection.execute(
            "INSERT INTO agents (id, tenant_id, name, atype, status, config, created_at) "
            "VALUES ('a1', 'acme', 'Legacy', 'worker', 'ready', '{}', CURRENT_TIMESTAMP)"
        )
        connection.commit()
        connection.close()
        command.upgrade(config, "head")
    finally:
        os.environ.pop("ALEMBIC_URL", None)

    connection = sqlite3.connect(database)
    enabled = connection.execute("SELECT enabled FROM agents WHERE id = 'a1'").fetchone()[0]
    columns = {row[1]: row for row in connection.execute("PRAGMA table_info('agents')")}
    indexes = {row[1] for row in connection.execute("PRAGMA index_list('agent_state_audit')")}
    connection.close()
    assert enabled == 1
    assert columns["enabled"][3] == 1
    assert {
        "ix_agent_state_audit_tenant_id",
        "ix_agent_state_audit_agent_id",
        "ix_agent_state_audit_created_at",
        "ix_agent_state_audit_tenant_agent_created",
    } <= indexes


def test_openapi_artifacts_document_worker_controls_and_csrf(client):
    root = Path(__file__).parents[1]
    runtime = client.app.openapi()
    core_spec = json.loads((root / "openapi.json").read_text())
    generated = (root.parent / "frontend/packages/api-client/src/schema.d.ts").read_text()

    assert core_spec == runtime
    assert "/api/v1/agents/usage" in runtime["paths"]
    assert "/api/v1/admin/me" in runtime["paths"]
    operations = [
        runtime["paths"][
            "/api/v1/admin/customers/{customer_id}/workers/{agent_id}/enabled"
        ]["patch"],
        runtime["paths"]["/api/v1/admin/customers/{user_id}/studio"]["post"],
        runtime["paths"]["/api/v1/admin/customers/{user_id}"]["delete"],
    ]
    for operation in operations:
        parameters = operation["parameters"]
        assert any(
            parameter["in"] == "header"
            and parameter["name"] == "X-CSRF-Token"
            and parameter["required"] is True
            for parameter in parameters
        )
        assert any(
            parameter["in"] == "cookie"
            and parameter["name"] == "qiko_csrf"
            and parameter["required"] is True
            for parameter in parameters
        )
    assert "AgentUsage" in runtime["components"]["schemas"]
    assert "WorkerEnabledBody" in runtime["components"]["schemas"]
    assert "AgentUsage" in generated and "WorkerEnabledBody" in generated
    assert '"X-CSRF-Token": string' in generated
    assert 'qiko_csrf: string' in generated


def test_inactive_subscription_displays_free_plan(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'customer.db'}")
    Base.metadata.create_all(engine)
    sm = sessionmaker(engine, expire_on_commit=False)
    with sm() as session, session.begin():
        session.add(TenantRow(id="acme", name="Acme"))
    SqlSubscriptionStore(sm).put(Subscription("acme", "pro", "canceled"))

    assert SqlCustomerDirectory(sm).details("acme").plan == "free"
