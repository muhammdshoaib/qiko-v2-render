"""Folding the two older audit tables into the unified stream.

Until now "one stream" was not true. Worker availability lived in agent_state_audit and platform access
in platform_admin_audit, so the audit page and every activity panel were incomplete, and the panel had to
carry a note disclaiming what it did not show. A trail that needs a disclaimer is one an operator cannot
reason from.

Both legacy tables are still written. Their shapes are what two existing UIs render, so removing them
would bundle a UI change into a data change; what "one stream" requires is that the unified trail is
COMPLETE, not that the old tables are gone. Retiring them is a follow-up once nothing reads them.
"""
import asyncio

from app.modules.agents.service import Agent
from app.modules.audit import registry
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import Capability
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN = "fold-admin.invalid"


def _admin(client) -> tuple[dict, dict]:
    bootstrap_admin(client, ADMIN)
    token = csrf.generate_csrf_token()
    return ({**auth_cookies("platform", "owner", email=ADMIN), csrf.CSRF_COOKIE: token},
            {csrf.CSRF_HEADER: token})


def _rows(client, action: str) -> list[dict]:
    return [r for r in client.app.state.audit.rows if r["action"] == action]


def _seed(client) -> None:
    from app.modules.admin.customers import CustomerRecord

    client.app.state.customers.add(CustomerRecord("acme", "owner@acme.invalid", "pro"))
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="w1", tenant="acme", name="Tender Bot")))


# --- worker availability ---------------------------------------------------------------------------

def test_disabling_a_worker_lands_in_the_unified_stream(client):
    cookies, headers = _admin(client)
    _seed(client)
    response = client.patch("/api/v1/admin/customers/acme/workers/w1/enabled",
                            cookies=cookies, headers=headers,
                            json={"enabled": False, "reason": "runaway spend"})
    assert response.status_code == 200

    row = _rows(client, registry.WORKER_ENABLED_CHANGED)[0]
    assert row["changes"]["enabled"] == {"from": True, "to": False}
    assert row["target_id"] == "w1" and row["target_label"] == "Tender Bot"
    assert row["tenant_id"] == "acme"
    assert row["actor_label"] == ADMIN
    assert row["actor_type"] == "platform_admin", "this path is only reachable from the console"
    assert row["reason"] == "runaway spend"


def test_the_legacy_table_still_has_its_row_too(client):
    """Both are written. The customer detail view renders the legacy shape, so removing it would bundle
    a UI change into a data change."""
    cookies, headers = _admin(client)
    _seed(client)
    client.patch("/api/v1/admin/customers/acme/workers/w1/enabled", cookies=cookies,
                 headers=headers, json={"enabled": False, "reason": "x"})

    legacy = asyncio.run(client.app.state.agents.store.list_state_audit("acme"))
    assert len(legacy) == 1 and legacy[0].agent_id == "w1"
    assert len(_rows(client, registry.WORKER_ENABLED_CHANGED)) == 1


def test_a_no_op_toggle_writes_neither_row(client):
    """The legacy path already suppressed no-ops. Folding in must not make the unified stream noisier
    than the table it is replacing."""
    cookies, headers = _admin(client)
    _seed(client)
    client.patch("/api/v1/admin/customers/acme/workers/w1/enabled", cookies=cookies,
                 headers=headers, json={"enabled": True, "reason": "already available"})
    assert _rows(client, registry.WORKER_ENABLED_CHANGED) == []
    assert asyncio.run(client.app.state.agents.store.list_state_audit("acme")) == []


# --- platform access -------------------------------------------------------------------------------

def test_a_grant_lands_in_the_unified_stream_with_its_capability_set(client):
    """The capability SETS are the substance, not just the role: the whole reason platform admins have
    capabilities is that "super_admin or nothing" was too blunt, so a row recording only the role would
    hide the change that actually happened most of the time."""
    cookies, headers = _admin(client)
    client.put("/api/v1/admin/org/helper@invalid", cookies=cookies, headers=headers,
               json={"role": "viewer", "capabilities": [Capability.manage_workers.value],
                     "reason": "cost review"})

    row = _rows(client, registry.PLATFORM_ACCESS_GRANTED)[0]
    assert row["target_id"] == "helper@invalid"
    assert row["changes"]["role"] == {"from": None, "to": "viewer"}
    assert row["changes"]["capabilities"]["to"] == ["manage_workers"]
    assert row["reason"] == "cost review"


def test_a_revoke_records_what_the_admin_had(client):
    """Read before the delete: afterwards the role and capability set are unrecoverable, which is the
    same ordering the tenant hard delete had to get right."""
    cookies, headers = _admin(client)
    client.put("/api/v1/admin/org/helper@invalid", cookies=cookies, headers=headers,
               json={"role": "viewer", "capabilities": [Capability.view_customers.value]})
    client.delete("/api/v1/admin/org/helper@invalid", cookies=cookies,
                  headers={**headers, "x-audit-reason": "left the team"})

    row = _rows(client, registry.PLATFORM_ACCESS_REVOKED)[0]
    assert row["changes"]["role"] == {"from": "viewer", "to": None}
    assert row["changes"]["capabilities"]["from"] == ["view_customers"]
    assert row["reason"] == "left the team"


def test_platform_access_rows_stay_behind_manage_admins(client):
    """They carry capability sets, which is the scope of someone's authority. Folding them into the
    shared stream must not widen who can read them."""
    cookies, headers = _admin(client)
    client.put("/api/v1/admin/org/helper@invalid", cookies=cookies, headers=headers,
               json={"role": "viewer", "capabilities": [Capability.view_customers.value]})
    client.put("/api/v1/admin/org/narrow@invalid", cookies=cookies, headers=headers,
               json={"role": "viewer", "capabilities": [Capability.view_audit.value,
                                                       Capability.view_customers.value]})

    narrow = auth_cookies("platform", "viewer", email="narrow@invalid")
    visible = client.get("/api/v1/admin/audit?days=1", cookies=narrow).json()
    assert all(not e["action"].startswith("access.platform_") for e in visible["items"])
    assert visible["hidden_actions"] > 0


# --- the property that made folding worth doing ------------------------------------------------------

def test_both_writes_share_the_transaction_they_are_folded_into():
    """The legacy rows were written inside a row-locked transaction, which is why they could not be
    lost. Folding in would have been a downgrade if the unified row were written afterwards."""
    import inspect

    from app.db.stores import SqlAdminOrgStore, SqlAgentStore

    enabled = inspect.getsource(SqlAgentStore.set_enabled)
    assert enabled.count("async with self.sessionmaker() as s, s.begin():") == 1
    assert "with_for_update()" in enabled
    assert "s.add(AuditEventRow(**_worker_availability_row(" in enabled

    revoke = inspect.getsource(SqlAdminOrgStore.revoke)
    assert "s.add(AuditEventRow(**_platform_access_row(" in revoke
    # Before the delete, or the role and capabilities are gone.
    assert revoke.index("_platform_access_row(") < revoke.index("await s.delete(row)")


def test_the_activity_panel_no_longer_disclaims_a_gap():
    """It had to carry a note saying availability changes were not in this stream. Now they are, so the
    note is gone: a panel that keeps disclaiming a gap it no longer has teaches operators to distrust
    it."""
    from pathlib import Path

    admin = Path(__file__).resolve().parents[2] / "frontend" / "apps" / "admin"
    dialog = (admin / "components" / "customer-detail-dialog.tsx").read_text()
    assert "note=" not in dialog
    for page in ("tenants", "workers"):
        source = (admin / "app" / page / "page.tsx").read_text()
        assert "note=" not in source, f"{page} still disclaims a gap"
