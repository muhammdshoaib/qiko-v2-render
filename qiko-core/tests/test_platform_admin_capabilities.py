"""QIK-513: fine-grained platform-admin capabilities, a real admin directory, and an audit trail.

Before this, platform admin was all-or-nothing (super_admin/viewer), there was no way to enumerate
who had access, grants left no trail, and /admin/org/accept had no authentication at all - anyone
holding a leaked invite could mint platform-admin access for the invited email.
"""
import asyncio

import pytest

from app.modules.identity import csrf
from app.modules.identity.admin_rbac import (
    AdminAuthzError,
    AdminOrg,
    AdminRole,
    Capability,
    default_capabilities,
    effective_capabilities,
    parse_capabilities,
)
from tests.helpers import auth_cookies, bootstrap_admin

BOSS = "boss.caps@invalid"
HELPER = "helper.caps@invalid"


def _csrf(cookies: dict) -> tuple[dict, dict]:
    token = csrf.generate_csrf_token()
    return {**cookies, csrf.CSRF_COOKIE: token}, {csrf.CSRF_HEADER: token}


def _boss(client) -> dict:
    bootstrap_admin(client, BOSS)
    # tenant role deliberately "viewer": platform access must never come from the tenant role
    return auth_cookies("plat", "viewer", email=BOSS)


# --- the capability model itself -----------------------------------------------------------------

def test_role_defaults_keep_todays_behaviour():
    assert default_capabilities(AdminRole.super_admin) == frozenset(Capability)
    assert default_capabilities(AdminRole.viewer) == frozenset({Capability.view_customers})


def test_an_explicit_grant_overrides_the_role_default():
    granted = effective_capabilities(AdminRole.viewer, {Capability.manage_workers})
    assert granted == {Capability.manage_workers}, "a viewer can hold exactly one extra capability"
    assert Capability.manage_customers not in granted


def test_a_super_admin_can_never_lose_admin_management():
    """Narrowing the last super_admin below manage_admins would leave the platform unrecoverable
    without a database edit."""
    narrowed = effective_capabilities(AdminRole.super_admin, {Capability.view_customers})
    assert Capability.manage_admins in narrowed


def test_unknown_capability_names_are_rejected_not_dropped():
    assert parse_capabilities(None) is None
    assert parse_capabilities(["manage_workers"]) == {Capability.manage_workers}
    with pytest.raises(ValueError):
        parse_capabilities(["manage_workers", "not_a_capability"])


def test_an_admin_cannot_touch_their_own_access_at_all():
    """Not just their role: self-WIDENING kept the role column unchanged, so a role-based review
    would have shown nothing while the actor quietly gained every capability."""
    org = AdminOrg()

    async def scenario():
        await org.bootstrap_super_admin(BOSS)
        with pytest.raises(AdminAuthzError):
            await org.grant(BOSS, BOSS, AdminRole.viewer, None)
        with pytest.raises(AdminAuthzError):  # same role, wider capabilities
            await org.grant(BOSS, BOSS, AdminRole.super_admin, frozenset(Capability))
        with pytest.raises(AdminAuthzError):
            await org.revoke(BOSS, BOSS)

    asyncio.run(scenario())


def test_manage_admins_is_not_a_delegable_root_primitive():
    """A viewer granted only "manage admins" must not become root by proxy: minting a super_admin,
    demoting a peer super_admin (bypassing the removal path's 409), or delegating manage_admins on."""
    org = AdminOrg()

    async def scenario():
        await org.bootstrap_super_admin(BOSS)
        # Given BOTH manage_admins and view_customers, so the positive case below is about authority
        # limits rather than simply lacking the capability.
        await org.grant(BOSS, HELPER, AdminRole.viewer,
                        frozenset({Capability.manage_admins, Capability.view_customers}))

        # cannot appoint a super_admin
        with pytest.raises(AdminAuthzError):
            await org.grant(HELPER, "puppet@invalid", AdminRole.super_admin, None)
        # cannot demote or otherwise change an existing super_admin
        with pytest.raises(AdminAuthzError):
            await org.grant(HELPER, BOSS, AdminRole.viewer, frozenset())
        # cannot remove a super_admin either
        with pytest.raises(AdminAuthzError):
            await org.revoke(HELPER, BOSS)
        # cannot pass manage_admins on to someone else
        with pytest.raises(AdminAuthzError):
            await org.grant(HELPER, "third@invalid", AdminRole.viewer,
                            frozenset({Capability.manage_admins}))
        # cannot hand out a capability it does not hold itself, so it cannot build a puppet with
        # more authority than the granter has
        with pytest.raises(AdminAuthzError):
            await org.grant(HELPER, "puppet2@invalid", AdminRole.viewer,
                            frozenset({Capability.manage_customers}))
        # what it CAN do: pass on a capability it holds, to an ordinary viewer
        managed = await org.grant(HELPER, "ordinary@invalid", AdminRole.viewer,
                                  frozenset({Capability.view_customers}))
        assert managed.capabilities == {Capability.view_customers}

    asyncio.run(scenario())


def test_a_narrowed_admin_really_loses_server_side_access(client):
    """The capabilities must gate real endpoints, not just the menu: a super_admin narrowed away from
    manage_customers has to be refused by the API, otherwise "least privilege" is only a UI filter."""
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    # A SUPER_ADMIN narrowed to reads only: the role alone would allow every mutation, so this is
    # the property the feature is sold on. Granting a viewer would have proven nothing, since a
    # viewer was already refused these endpoints before capabilities existed.
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
               json={"role": "super_admin", "capabilities": ["view_customers"]})
    helper = auth_cookies("plat", "owner", email=HELPER)
    helper_csrf, helper_headers = _csrf(helper)

    # reads it still holds
    assert client.get("/api/v1/admin/customers", cookies=helper).status_code == 200
    # mutations it does not
    assert client.delete("/api/v1/admin/customers/someone", cookies=helper_csrf,
                         headers=helper_headers).status_code == 403
    assert client.post("/api/v1/billing/payment-links", cookies=helper_csrf, headers=helper_headers,
                       json={"email": "x@invalid", "amount_cents": 100,
                             "description": "d"}).status_code == 403


def test_an_admin_with_no_capabilities_loses_reads_too(client):
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
               json={"role": "viewer", "capabilities": []})
    helper = auth_cookies("plat", "owner", email=HELPER)
    assert client.get("/api/v1/admin/customers", cookies=helper).status_code == 403


def test_a_reserved_path_segment_cannot_become_an_admin(client):
    """PUT /admin/org/audit used to create a platform_admins row literally keyed "audit"."""
    with_csrf, headers = _csrf(_boss(client))
    assert client.put("/api/v1/admin/org/audit", cookies=with_csrf, headers=headers,
                      json={"role": "viewer"}).status_code == 422
    assert client.put(f"/api/v1/admin/org/{'a' * 400}@x.invalid", cookies=with_csrf,
                      headers=headers, json={"role": "viewer"}).status_code == 422


def test_mutations_require_csrf(client):
    cookies = _boss(client)
    assert client.put(f"/api/v1/admin/org/{HELPER}", cookies=cookies,
                      json={"role": "viewer"}).status_code == 403
    assert client.delete(f"/api/v1/admin/org/{HELPER}", cookies=cookies).status_code == 403


def test_a_tenant_owner_is_refused_on_every_new_endpoint(client):
    outsider = auth_cookies("other", "owner", email="outsider2@invalid")
    with_csrf, headers = _csrf(outsider)
    assert client.get("/api/v1/admin/org", cookies=outsider).status_code == 403
    assert client.get("/api/v1/admin/org/audit", cookies=outsider).status_code == 403
    assert client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
                      json={"role": "super_admin"}).status_code == 403
    assert client.delete(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf,
                         headers=headers).status_code == 403


def test_invite_and_accept_stay_dev_only(client, monkeypatch):
    """They mint a stateless, replayable, unrevocable 7-day bearer credential for the highest
    privilege in the system, and nothing in the product calls them. Production granting goes through
    the audited PUT, and first-admin provisioning through the operator CLI."""
    from app.core.config import Environment, get_settings

    monkeypatch.setattr(get_settings(), "environment", Environment.preprod)
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    assert client.post("/api/v1/admin/org/invite", cookies=with_csrf, headers=headers,
                       json={"email": HELPER, "role": "viewer"}).status_code == 404
    assert client.post("/api/v1/admin/org/accept", cookies=cookies,
                       json={"token": "anything"}).status_code == 404


def test_a_no_op_grant_writes_no_audit_row(client):
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    body = {"role": "viewer", "capabilities": ["view_customers"]}
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers, json=body)
    first = len(client.get("/api/v1/admin/org/audit", cookies=cookies).json()["entries"])
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers, json=body)
    assert len(client.get("/api/v1/admin/org/audit", cookies=cookies).json()["entries"]) == first


def test_the_audit_records_the_effective_capabilities_not_the_requested_ones(client):
    """A super_admin implicitly keeps manage_admins; storing the requested list without it made the
    directory and the audit disagree about the real authority."""
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
               json={"role": "super_admin", "capabilities": ["view_customers"]})
    entry = client.get("/api/v1/admin/org/audit", cookies=cookies).json()["entries"][0]
    assert "manage_admins" in entry["capabilities"]


def test_grant_and_revoke_are_row_locked_in_the_sql_store():
    """The API tests run against the in-memory store, so pin the production locking at the source:
    losing FOR UPDATE would let two concurrent grants interleave."""
    import inspect

    from app.db.stores import SqlAdminOrgStore

    for method in (SqlAdminOrgStore.grant, SqlAdminOrgStore.revoke):
        source = inspect.getsource(method)
        assert "with_for_update()" in source
        assert "s.begin()" in source


def test_only_manage_admins_can_grant():
    org = AdminOrg()

    async def scenario():
        await org.bootstrap_super_admin(BOSS)
        await org.grant(BOSS, HELPER, AdminRole.viewer, None)
        with pytest.raises(AdminAuthzError):
            await org.grant(HELPER, "third@invalid", AdminRole.super_admin, None)

    asyncio.run(scenario())


# --- the API ------------------------------------------------------------------------------------

def test_directory_lists_every_platform_admin_with_effective_capabilities(client):
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    granted = client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
                         json={"role": "viewer", "capabilities": ["manage_workers"],
                               "reason": "cost review only"})
    assert granted.status_code == 200
    assert granted.json() == {"email": HELPER, "role": "viewer", "capabilities": ["manage_workers"]}

    listed = client.get("/api/v1/admin/org", cookies=cookies)
    assert listed.status_code == 200
    admins = {entry["email"]: entry for entry in listed.json()["admins"]}
    assert set(admins) == {BOSS, HELPER}
    assert admins[HELPER]["capabilities"] == ["manage_workers"]
    assert "manage_customers" in admins[BOSS]["capabilities"]


def test_grants_and_revokes_are_audited_with_before_and_after(client):
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
               json={"role": "viewer", "capabilities": ["manage_workers"], "reason": "cost review"})
    # Revoking platform access is the highest-privilege action here, so its reason is the last one
    # that should end up in an edge access log. It travels in a header.
    client.delete(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf,
                  headers={**headers, "x-audit-reason": "left the team"})

    entries = client.get("/api/v1/admin/org/audit", cookies=cookies).json()["entries"]
    assert len(entries) >= 2
    revoke, grant = entries[0], entries[1]
    assert revoke["email"] == HELPER and revoke["role"] is None
    assert revoke["previous_role"] == "viewer" and revoke["reason"] == "left the team"
    assert grant["role"] == "viewer" and grant["capabilities"] == ["manage_workers"]
    assert grant["changed_by_email"] == BOSS and grant["reason"] == "cost review"


def test_an_unknown_capability_is_a_422_not_a_silent_narrowing(client):
    with_csrf, headers = _csrf(_boss(client))
    r = client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
                   json={"role": "viewer", "capabilities": ["manage_workers", "nope"]})
    assert r.status_code == 422


def test_capability_denial_never_mentions_mfa(client):
    """The admin shell redirects to 2FA onboarding when a 403 body matches /mfa/i, so a capability
    denial must not be mistaken for a missing-2FA state or the admin lands in an enrolment loop."""
    bootstrap_admin(client, BOSS)
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
               json={"role": "viewer", "capabilities": []})

    helper = auth_cookies("plat", "owner", email=HELPER)
    helper_csrf, helper_headers = _csrf(helper)
    denied = client.put("/api/v1/admin/org/third@invalid", cookies=helper_csrf,
                        headers=helper_headers, json={"role": "viewer"})
    assert denied.status_code == 403
    assert "mfa" not in denied.json()["detail"].lower()
    assert "capability" in denied.json()["detail"]


def test_directory_and_audit_are_closed_to_non_platform_admins(client):
    outsider = auth_cookies("other", "owner", email="outsider@invalid")
    assert client.get("/api/v1/admin/org", cookies=outsider).status_code == 403
    assert client.get("/api/v1/admin/org/audit", cookies=outsider).status_code == 403


def test_admin_me_reports_capabilities_so_the_ui_can_hide_what_is_denied(client):
    cookies = _boss(client)
    body = client.get("/api/v1/admin/me", cookies=cookies).json()
    assert body["role"] == "super_admin"
    assert "manage_admins" in body["capabilities"] and "manage_workers" in body["capabilities"]


def test_an_unknown_stored_capability_narrows_instead_of_500ing():
    """A stored name this build does not know (a rollback past a release that added one) must not
    turn one row into a 500 for /admin/me, the whole directory and the capability gate itself.
    Dropping it narrows the admin's access, which is the safe direction."""
    from app.modules.identity.admin_rbac import read_capabilities

    assert read_capabilities(None) is None
    assert read_capabilities(["view_customers", "from_the_future"]) == {Capability.view_customers}
    assert read_capabilities(["from_the_future"]) == frozenset()
    # the INPUT path stays strict, so a typo in a grant is still refused
    with pytest.raises(ValueError):
        parse_capabilities(["from_the_future"])


def test_an_admin_cannot_grant_a_capability_they_do_not_hold():
    """Otherwise a viewer holding only manage_admins could give a puppet identity every other
    capability and then sign in as it."""
    org = AdminOrg()

    async def scenario():
        await org.bootstrap_super_admin(BOSS)
        await org.grant(BOSS, HELPER, AdminRole.viewer, frozenset({Capability.manage_admins}))
        with pytest.raises(AdminAuthzError):
            await org.grant(HELPER, "puppet@invalid", AdminRole.viewer,
                            frozenset({Capability.manage_customers}))
        # a super_admin holds everything, so the rule never restricts them
        wide = await org.grant(BOSS, "ok@invalid", AdminRole.viewer,
                               frozenset({Capability.manage_customers}))
        assert wide.capabilities == {Capability.manage_customers}

    asyncio.run(scenario())


def test_the_directory_and_audit_need_manage_admins_not_merely_membership(client):
    """They expose every admin's capabilities and the free-text reasons behind each change, which
    will carry sensitive wording. An admin narrowed to reads of customers should not see them."""
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
               json={"role": "viewer", "capabilities": ["view_customers"]})
    helper = auth_cookies("plat", "owner", email=HELPER)
    assert client.get("/api/v1/admin/customers", cookies=helper).status_code == 200
    assert client.get("/api/v1/admin/org", cookies=helper).status_code == 403
    assert client.get("/api/v1/admin/org/audit", cookies=helper).status_code == 403
