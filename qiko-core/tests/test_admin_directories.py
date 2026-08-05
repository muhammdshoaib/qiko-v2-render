"""QIK-515 / QIK-516 / QIK-520: the three cross-tenant admin directories.

Each answers a question that previously required opening records one by one, or reading two tables by
hand:
- how many people and workers are on this account (the counts existed but were never surfaced)
- who can reach the admin panel, given that tenant RBAC and platform RBAC are separate systems
- which workers are disabled right now, across every tenant
"""
import asyncio

import pytest

from app.modules.admin.customers import CustomerRecord
from app.modules.admin.pagination import MAX_PAGE_SIZE, PAGE_SIZE, paginate
from app.modules.agents.service import Agent
from app.modules.identity.admin_rbac import AdminRole, Capability
from app.modules.identity.rbac import Role
from app.modules.identity.store import User
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN_EMAIL = "dir-admin.invalid"


def _admin(client) -> dict:
    bootstrap_admin(client, ADMIN_EMAIL)
    # tenant role deliberately "viewer": platform access must never come from the tenant role
    return auth_cookies("platform", "viewer", email=ADMIN_EMAIL)


def _seed(client) -> None:
    client.app.state.customers.add(CustomerRecord("acme", "owner@acme.invalid", "pro",
                                                  stripe_paid_cents=5000, agents=2, users=3))
    client.app.state.customers.add(CustomerRecord("beta", "owner@beta.invalid", "free", agents=1, users=1))

    async def seed() -> None:
        await client.app.state.agents.store.add(Agent(
            id="a1", tenant="acme", name="Tender writer",
            config={"expertise": "Tender writing", "system_prompt": "must-not-leak",
                    "nested": {"apiToken": "must-not-leak"}}))
        await client.app.state.agents.store.add(Agent(id="a2", tenant="acme", name="Disabled one",
                                                     enabled=False))
        await client.app.state.agents.store.add(Agent(id="b1", tenant="beta", name="Beta worker"))

    asyncio.run(seed())


def _seed_users(client) -> None:
    from app.core.deps import get_user_store

    async def seed() -> None:
        store = get_user_store()
        await store.add(User(id="u1", email="owner@acme.invalid", password_hash="x",
                             tenant="acme", role=Role.owner, name="Acme Owner"))
        await store.add(User(id="u2", email="editor@acme.invalid", password_hash="x",
                             tenant="acme", role=Role.editor, twofa_enabled=True))
        await store.add(User(id="u3", email="owner@beta.invalid", password_hash="x",
                             tenant="beta", role=Role.owner))
        await store.add(User(id="u4", email=ADMIN_EMAIL, password_hash="x",
                             tenant="platform", role=Role.viewer))

    asyncio.run(seed())


# --- pagination ----------------------------------------------------------------------------------

def test_a_zero_or_negative_page_no_longer_returns_the_wrong_slice():
    """page was unvalidated: page=0 computed a start offset of -20 and returned nothing alongside a
    non-zero total, and page=-1 silently returned the LAST rows of the directory."""
    rows = list(range(50))
    assert paginate(rows, page=0)["items"] == rows[:PAGE_SIZE]
    assert paginate(rows, page=-1)["items"] == rows[:PAGE_SIZE]
    assert paginate(rows, page=0)["page"] == 1


def test_page_size_is_bounded_so_one_request_cannot_ask_for_everything():
    rows = list(range(500))
    assert len(paginate(rows, page=1, page_size=10_000)["items"]) == MAX_PAGE_SIZE
    # 0 or None means "unspecified", so it falls back to the default page rather than to one row
    assert len(paginate(rows, page=1, page_size=0)["items"]) == PAGE_SIZE
    assert len(paginate(rows, page=1, page_size=-5)["items"]) == 1


def test_the_total_is_the_unpaginated_count():
    rows = list(range(50))
    result = paginate(rows, page=2, page_size=20)
    assert result["total"] == 50 and result["page"] == 2
    assert result["items"] == rows[20:40]


# --- QIK-515 tenant directory --------------------------------------------------------------------

def test_the_tenant_directory_reports_user_and_worker_counts(client):
    _seed(client)
    body = client.get("/api/v1/admin/tenants", cookies=_admin(client)).json()
    rows = {row["tenant_id"]: row for row in body["items"]}
    assert body["total"] == 2
    assert rows["acme"]["user_count"] == 3 and rows["acme"]["worker_count"] == 2
    assert rows["acme"]["plan"] == "pro" and rows["acme"]["earnings_cents"] == 5000
    assert rows["beta"]["user_count"] == 1 and rows["beta"]["worker_count"] == 1


def test_the_tenant_directory_search_filters(client):
    _seed(client)
    body = client.get("/api/v1/admin/tenants?search=beta", cookies=_admin(client)).json()
    assert [row["tenant_id"] for row in body["items"]] == ["beta"]


# --- QIK-516 user directory ----------------------------------------------------------------------

def test_the_user_directory_shows_both_rbac_systems_side_by_side(client):
    """Tenant role lives on users.role; platform access is keyed by email in a different table. An
    operator had no single place to see who could reach the admin panel."""
    cookies = _admin(client)
    _seed_users(client)
    body = client.get("/api/v1/admin/users", cookies=cookies).json()
    rows = {row["email"]: row for row in body["items"]}

    assert rows["owner@acme.invalid"]["role"] == "owner"
    assert rows["owner@acme.invalid"]["role_label"] == "Owner"
    assert rows["owner@acme.invalid"]["platform_role"] is None
    assert rows["editor@acme.invalid"]["twofa_enabled"] is True

    # the platform admin appears with its platform role AND its tenant role
    assert rows[ADMIN_EMAIL]["role"] == "viewer"
    assert rows[ADMIN_EMAIL]["platform_role"] == "super_admin"
    assert "manage_admins" in rows[ADMIN_EMAIL]["platform_capabilities"]


def test_the_user_directory_never_exposes_a_credential(client):
    cookies = _admin(client)
    _seed_users(client)
    raw = client.get("/api/v1/admin/users", cookies=cookies).text
    for secret in ("password_hash", "totp_secret", "current_sid", "password"):
        assert secret not in raw


def test_the_user_directory_filters_by_tenant(client):
    cookies = _admin(client)
    _seed_users(client)
    body = client.get("/api/v1/admin/users?tenant_id=acme", cookies=cookies).json()
    assert {row["email"] for row in body["items"]} == {"owner@acme.invalid", "editor@acme.invalid"}


# --- QIK-520 worker directory --------------------------------------------------------------------

def test_the_worker_directory_spans_tenants_and_names_the_owner(client):
    _seed(client)
    body = client.get("/api/v1/admin/workers", cookies=_admin(client)).json()
    rows = {row["id"]: row for row in body["items"]}
    assert body["total"] == 3
    assert rows["a1"]["tenant_id"] == "acme" and rows["b1"]["tenant_id"] == "beta"


def test_the_worker_directory_applies_the_same_config_allowlist(client):
    """A directory listing must not become a new leak path for worker configuration."""
    _seed(client)
    body = client.get("/api/v1/admin/workers", cookies=_admin(client)).json()
    assert body["items"] and "must-not-leak" not in client.get(
        "/api/v1/admin/workers", cookies=_admin(client)).text
    row = next(row for row in body["items"] if row["id"] == "a1")
    assert row["config"] == {"expertise": "Tender writing"}


def test_the_worker_directory_can_answer_which_workers_are_disabled(client):
    _seed(client)
    cookies = _admin(client)
    disabled = client.get("/api/v1/admin/workers?enabled=false", cookies=cookies).json()
    assert [row["id"] for row in disabled["items"]] == ["a2"]
    live = client.get("/api/v1/admin/workers?enabled=true", cookies=cookies).json()
    assert {row["id"] for row in live["items"]} == {"a1", "b1"}


# --- gating --------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/v1/admin/tenants", "/api/v1/admin/users",
                                  "/api/v1/admin/workers"])
def test_every_directory_is_closed_to_non_platform_admins(client, path):
    assert client.get(path, cookies=auth_cookies("acme", "owner")).status_code == 403
    assert client.get(path, cookies=auth_cookies("acme", "admin")).status_code == 403


@pytest.mark.parametrize("path", ["/api/v1/admin/tenants", "/api/v1/admin/users",
                                  "/api/v1/admin/workers"])
def test_every_directory_needs_view_customers_not_mere_membership(client, path):
    """An admin explicitly narrowed to zero capabilities must not be able to enumerate the platform."""
    from app.modules.identity import csrf

    cookies = _admin(client)
    token = csrf.generate_csrf_token()
    client.put("/api/v1/admin/org/narrow.dir@invalid",
               cookies={**cookies, csrf.CSRF_COOKIE: token},
               headers={csrf.CSRF_HEADER: token},
               json={"role": "viewer", "capabilities": []})
    narrowed = auth_cookies("platform", "owner", email="narrow.dir@invalid")
    assert client.get(path, cookies=narrowed).status_code == 403


def test_a_narrowed_admin_with_view_customers_can_read_the_directories(client):
    from app.modules.identity import csrf

    cookies = _admin(client)
    token = csrf.generate_csrf_token()
    client.put("/api/v1/admin/org/reader.dir@invalid",
               cookies={**cookies, csrf.CSRF_COOKIE: token},
               headers={csrf.CSRF_HEADER: token},
               json={"role": "viewer", "capabilities": [Capability.view_customers.value]})
    reader = auth_cookies("platform", "viewer", email="reader.dir@invalid")
    for path in ("/api/v1/admin/tenants", "/api/v1/admin/users", "/api/v1/admin/workers"):
        assert client.get(path, cookies=reader).status_code == 200
    # but it still cannot manage anything
    assert client.delete("/api/v1/admin/customers/acme", cookies=reader).status_code == 403


def test_the_cross_tenant_store_methods_are_explicitly_marked_as_such():
    """These are the only unfiltered queries in the data layer. There is no lint rule that catches an
    accidentally unscoped query, so the exemption is pinned here as well as commented."""
    import inspect

    from app.db.stores import SqlAgentStore, SqlUserStore

    for method in (SqlUserStore.list_all, SqlAgentStore.list_all):
        source = inspect.getsource(method)
        assert "Cross-tenant" in source
        assert "tenant_id ==" not in source, "list_all must not be tenant filtered"


def test_the_directory_roles_use_the_shared_labels():
    """So the admin console and the creator team screen never disagree about what a role is called."""
    from app.modules.identity.team_access import ROLE_LABELS

    assert ROLE_LABELS[Role.viewer] == "User"
    assert ROLE_LABELS[Role.owner] == "Owner"
    assert AdminRole.super_admin.value == "super_admin"
