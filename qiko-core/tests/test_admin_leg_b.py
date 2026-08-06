"""Leg B: sorting, filtering, page size, the two missing mutations, and audit coverage.

Three admin mutations left no trace, no directory could be sorted, page_size was never exposed despite
full store support, and two operations an operator obviously needs did not exist at all: changing any
user's tenant role from the console, and moving a worker back to training.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from app.modules.admin import audit
from app.modules.admin.sorting import USER_SORTS, apply_sort
from app.modules.agents.service import Agent
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import Capability
from app.modules.identity.rbac import Role
from app.modules.identity.store import User
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN = "legb-admin.invalid"


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
    """Ids are namespaced. An earlier version used "u-owner", which is the id tests/test_twofa_api.py
    authenticates as, so seeding it here made that file fail depending on execution order."""
    from app.core.deps import get_user_store

    async def seed() -> None:
        store = get_user_store()
        await store.add(User(id="legb-owner", email="owner@acme.invalid", password_hash="x",
                             tenant="acme", role=Role.owner, name="Zoe Owner"))
        await store.add(User(id="legb-viewer", email="viewer@acme.invalid", password_hash="x",
                             tenant="acme", role=Role.viewer, name="Al Viewer", twofa_enabled=True))
        await store.add(User(id="legb-editor", email="editor@beta.invalid", password_hash="x",
                             tenant="beta", role=Role.editor, name="Mia Editor"))
        await client.app.state.agents.store.add(
            Agent(id="w1", tenant="acme", name="Alpha worker", status="training"))
        await client.app.state.agents.store.add(
            Agent(id="w2", tenant="beta", name="Beta worker", status="ready", enabled=False))

    asyncio.run(seed())


# --- sorting -------------------------------------------------------------------------------------

def test_a_sort_field_outside_the_allowlist_is_refused_not_ignored():
    """A filter that quietly ignores what you asked for is worse than one that refuses, and an
    unvalidated key would let a caller order by a column the endpoint does not return."""
    rows = [{"email": "b@x", "name": "b", "tenant_id": "t", "role": "viewer", "twofa_enabled": False}]
    with pytest.raises(Exception) as error:
        apply_sort(rows, USER_SORTS, "password_hash", "asc")
    assert "cannot sort by" in str(error.value)


def test_no_sort_requested_keeps_the_existing_default_order():
    """Directories default to busiest-first or highest-earning-first. Sorting alphabetically the
    moment the parameter exists would silently change every screen."""
    rows = [{"email": "z@x", "name": "", "tenant_id": "", "role": "", "twofa_enabled": False},
            {"email": "a@x", "name": "", "tenant_id": "", "role": "", "twofa_enabled": False}]
    assert [r["email"] for r in apply_sort(rows, USER_SORTS, None, "asc")] == ["z@x", "a@x"]


def test_the_user_directory_sorts_by_an_allowlisted_field(client):
    _seed(client)
    cookies = _admin(client)
    body = client.get("/api/v1/admin/users?sort=email&order=desc", cookies=cookies).json()
    emails = [row["email"] for row in body["items"]]
    assert emails == sorted(emails, reverse=True)

    refused = client.get("/api/v1/admin/users?sort=password_hash", cookies=cookies)
    assert refused.status_code == 422
    assert "Sortable fields" in refused.json()["detail"]


@pytest.mark.parametrize("path", ["/api/v1/admin/users", "/api/v1/admin/workers",
                                  "/api/v1/admin/customers", "/api/v1/admin/tenants",
                                  "/api/v1/admin/worker-monitoring"])
def test_every_directory_accepts_a_bounded_page_size(client, path):
    """page_size was never exposed on any route despite the stores supporting it, so a client could
    not ask for more than twenty rows."""
    cookies = _admin(client)
    assert client.get(f"{path}?page_size=5", cookies=cookies).status_code == 200
    assert client.get(f"{path}?page_size=0", cookies=cookies).status_code == 422
    # MAX_PAGE_SIZE is the ceiling: one request must not be able to ask for the whole table.
    assert client.get(f"{path}?page_size=5000", cookies=cookies).status_code == 422
    body = client.get(f"{path}?page_size=5", cookies=cookies).json()
    assert body["page_size"] == 5 and len(body["items"]) <= 5


def test_the_new_filters_narrow_what_they_claim_to(client):
    _seed(client)
    cookies = _admin(client)
    by_role = client.get("/api/v1/admin/users?role=viewer", cookies=cookies).json()
    assert all(row["role"] == "viewer" for row in by_role["items"])

    without_2fa = client.get("/api/v1/admin/users?twofa=false", cookies=cookies).json()
    assert all(row["twofa_enabled"] is False for row in without_2fa["items"])

    training = client.get("/api/v1/admin/workers?status=training", cookies=cookies).json()
    assert all(row["status"] == "training" for row in training["items"])
    assert any(row["id"] == "w1" for row in training["items"])


def test_monitoring_can_finally_be_searched(client):
    _seed(client)
    body = client.get("/api/v1/admin/worker-monitoring?search=alpha", cookies=_admin(client)).json()
    assert [row["id"] for row in body["items"]] == ["w1"]


# --- cross-tenant role assignment ------------------------------------------------------------------

def test_an_admin_can_change_a_users_role_in_any_tenant(client):
    """The tenant-facing endpoint reads the tenant from the caller's own token, so a platform admin
    could only change users in the tenant they were signed into. There was no cross-tenant path."""
    _seed(client)
    with_csrf, headers = _csrf(_admin(client))
    response = client.put("/api/v1/admin/users/legb-editor/role", cookies=with_csrf, headers=headers,
                          json={"role": "admin", "reason": "promoted by support"})
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin" and body["previous_role"] == "editor" and body["tenant_id"] == "beta"


def test_the_owner_invariants_survive_the_new_path(client):
    """These are correctness rules, not permission checks: a tenant with no owner cannot administer
    itself, and a second owner is not a thing the model supports."""
    _seed(client)
    with_csrf, headers = _csrf(_admin(client))
    assert client.put("/api/v1/admin/users/legb-owner/role", cookies=with_csrf, headers=headers,
                      json={"role": "viewer"}).status_code == 409
    assert client.put("/api/v1/admin/users/legb-viewer/role", cookies=with_csrf, headers=headers,
                      json={"role": "owner"}).status_code == 422


def test_role_change_is_audited_with_before_and_after(client):
    """Nothing recorded a tenant role change anywhere, on either endpoint."""
    _seed(client)
    with_csrf, headers = _csrf(_admin(client))
    client.put("/api/v1/admin/users/legb-editor/role", cookies=with_csrf, headers=headers,
               json={"role": "admin", "reason": "support request 41"})
    trail = client.get("/api/v1/admin/audit?action=tenant_role_changed", cookies=_admin(client)).json()
    entry = trail["items"][0]
    assert entry["before"] == "editor" and entry["after"] == "admin"
    assert entry["actor_email"] == ADMIN and entry["reason"] == "support request 41"


def test_changing_a_role_needs_manage_customers_and_csrf(client):
    _seed(client)
    reader = _grant(client, "ro.legb@invalid", [Capability.view_customers.value])
    with_csrf, headers = _csrf(reader)
    assert client.put("/api/v1/admin/users/legb-editor/role", cookies=with_csrf, headers=headers,
                      json={"role": "admin"}).status_code == 403
    assert client.put("/api/v1/admin/users/legb-editor/role", cookies=_admin(client),
                      json={"role": "admin"}).status_code == 403


# --- worker status ----------------------------------------------------------------------------------

def test_a_worker_can_finally_be_moved_back_to_training(client):
    """mark_ready hardcodes "ready" and is one-way, so a worker whose ingest produced a bad corpus
    stayed advertised as ready and the only remedy was to disable it entirely."""
    _seed(client)
    with_csrf, headers = _csrf(_admin(client))
    response = client.put("/api/v1/admin/workers/beta/w2/status", cookies=with_csrf, headers=headers,
                          json={"status": "training", "reason": "corpus rebuild"})
    assert response.status_code == 200
    assert response.json()["status"] == "training" and response.json()["changed"] is True


def test_an_unknown_status_is_refused(client):
    _seed(client)
    with_csrf, headers = _csrf(_admin(client))
    response = client.put("/api/v1/admin/workers/acme/w1/status", cookies=with_csrf, headers=headers,
                          json={"status": "banana"})
    assert response.status_code == 422 and "Allowed" in response.json()["detail"]


def test_setting_the_same_status_is_a_no_op_and_writes_no_audit_row(client):
    _seed(client)
    with_csrf, headers = _csrf(_admin(client))
    response = client.put("/api/v1/admin/workers/acme/w1/status", cookies=with_csrf, headers=headers,
                          json={"status": "training"})
    assert response.json()["changed"] is False
    trail = client.get("/api/v1/admin/audit?action=worker_status_changed", cookies=_admin(client)).json()
    assert trail["items"] == []


def test_worker_status_needs_manage_workers(client):
    _seed(client)
    reader = _grant(client, "ro.status@invalid", [Capability.view_customers.value])
    with_csrf, headers = _csrf(reader)
    assert client.put("/api/v1/admin/workers/acme/w1/status", cookies=with_csrf, headers=headers,
                      json={"status": "ready"}).status_code == 403


# --- audit coverage ---------------------------------------------------------------------------------

def test_the_previously_silent_mutations_now_leave_a_trace(client):
    """Studio toggle, soft delete and cost caps recorded nothing at all. Soft delete hides a tenant
    platform-wide and has no reversal endpoint; a cap can stop a customer's workers answering."""
    _seed(client)
    cookies = _admin(client)
    with_csrf, headers = _csrf(cookies)
    client.put("/api/v1/admin/cost-caps/acme", cookies=with_csrf, headers=headers,
               json={"monthly_cap_usd": 5})
    client.delete("/api/v1/admin/cost-caps/acme", cookies=with_csrf, headers=headers)

    actions = {entry["action"] for entry in
               client.get("/api/v1/admin/audit", cookies=cookies).json()["items"]}
    assert {"cost_cap_set", "cost_cap_removed"} <= actions


def test_an_audit_write_failure_never_fails_the_mutation():
    """The mutation is already committed and its result already returned. Telling an operator their
    change failed when it did not, and having them repeat it, is worse than losing an audit row."""
    class Broken:
        async def add(self, _entry):
            raise RuntimeError("audit table is gone")

    entry = audit.AdminAction(action=audit.STUDIO_TOGGLED, target_type="tenant", target_id="acme",
                              actor_email="a@b", created_at=datetime.now(timezone.utc))
    asyncio.run(audit.record(Broken(), entry))  # must not raise


def test_the_audit_trail_is_filterable(client):
    _seed(client)
    cookies = _admin(client)
    with_csrf, headers = _csrf(cookies)
    client.put("/api/v1/admin/users/legb-editor/role", cookies=with_csrf, headers=headers,
               json={"role": "admin"})
    client.put("/api/v1/admin/cost-caps/beta", cookies=with_csrf, headers=headers,
               json={"monthly_cap_usd": 1})

    by_action = client.get("/api/v1/admin/audit?action=tenant_role_changed", cookies=cookies).json()
    assert all(e["action"] == "tenant_role_changed" for e in by_action["items"])
    by_tenant = client.get("/api/v1/admin/audit?tenant_id=beta", cookies=cookies).json()
    assert all(e["tenant_id"] == "beta" for e in by_tenant["items"])


def test_every_recorded_action_is_a_known_one():
    """A free-form action string means an audit row nobody can find later."""
    assert audit.STUDIO_TOGGLED in audit.ACTIONS
    assert len(audit.ACTIONS) == 6
