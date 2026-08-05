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
    granted = effective_capabilities(AdminRole.viewer, {Capability.view_ai_cost})
    assert granted == {Capability.view_ai_cost}, "a viewer can hold exactly one extra capability"
    assert Capability.manage_customers not in granted


def test_a_super_admin_can_never_lose_admin_management():
    """Narrowing the last super_admin below manage_admins would leave the platform unrecoverable
    without a database edit."""
    narrowed = effective_capabilities(AdminRole.super_admin, {Capability.view_customers})
    assert Capability.manage_admins in narrowed


def test_unknown_capability_names_are_rejected_not_dropped():
    assert parse_capabilities(None) is None
    assert parse_capabilities(["view_ai_cost"]) == {Capability.view_ai_cost}
    with pytest.raises(ValueError):
        parse_capabilities(["view_ai_cost", "not_a_capability"])


def test_an_admin_cannot_change_or_remove_themselves():
    org = AdminOrg()

    async def scenario():
        await org.bootstrap_super_admin(BOSS)
        with pytest.raises(AdminAuthzError):
            await org.grant(BOSS, BOSS, AdminRole.viewer, None)
        with pytest.raises(AdminAuthzError):
            await org.revoke(BOSS, BOSS)

    asyncio.run(scenario())


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
                         json={"role": "viewer", "capabilities": ["view_ai_cost"],
                               "reason": "cost review only"})
    assert granted.status_code == 200
    assert granted.json() == {"email": HELPER, "role": "viewer", "capabilities": ["view_ai_cost"]}

    listed = client.get("/api/v1/admin/org", cookies=cookies)
    assert listed.status_code == 200
    admins = {entry["email"]: entry for entry in listed.json()["admins"]}
    assert set(admins) == {BOSS, HELPER}
    assert admins[HELPER]["capabilities"] == ["view_ai_cost"]
    assert "manage_customers" in admins[BOSS]["capabilities"]


def test_grants_and_revokes_are_audited_with_before_and_after(client):
    cookies = _boss(client)
    with_csrf, headers = _csrf(cookies)
    client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
               json={"role": "viewer", "capabilities": ["view_ai_cost"], "reason": "cost review"})
    client.delete(f"/api/v1/admin/org/{HELPER}?reason=left+the+team",
                  cookies=with_csrf, headers=headers)

    entries = client.get("/api/v1/admin/org/audit", cookies=cookies).json()["entries"]
    assert len(entries) >= 2
    revoke, grant = entries[0], entries[1]
    assert revoke["email"] == HELPER and revoke["role"] is None
    assert revoke["previous_role"] == "viewer" and revoke["reason"] == "left the team"
    assert grant["role"] == "viewer" and grant["capabilities"] == ["view_ai_cost"]
    assert grant["changed_by_email"] == BOSS and grant["reason"] == "cost review"


def test_an_unknown_capability_is_a_422_not_a_silent_narrowing(client):
    with_csrf, headers = _csrf(_boss(client))
    r = client.put(f"/api/v1/admin/org/{HELPER}", cookies=with_csrf, headers=headers,
                   json={"role": "viewer", "capabilities": ["view_ai_cost", "nope"]})
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
    assert "manage_admins" in body["capabilities"] and "view_ai_cost" in body["capabilities"]
