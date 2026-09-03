"""QIKO-1048 Phase 1: shape-parity tests for app/modules/identity/admin_org_router.py."""
from tests.helpers import auth_cookies, bootstrap_admin
from app.modules.identity import csrf


def _super_admin(client) -> dict:
    email = "org-response-models-admin.invalid"
    bootstrap_admin(client, email)
    return auth_cookies("t", "viewer", email=email)


def _with_csrf(cookies: dict) -> tuple[dict, dict]:
    token = csrf.generate_csrf_token()
    return {**cookies, csrf.CSRF_COOKIE: token}, {csrf.CSRF_HEADER: token}


def test_bootstrap_shape(client):
    body = client.post("/api/v1/admin/org/bootstrap", cookies=auth_cookies("t", "owner")).json()
    assert set(body) == {"super_admin"}


def test_invite_and_accept_shape(client):
    admin = _super_admin(client)
    cookies, headers = _with_csrf(admin)
    invite_body = client.post(
        "/api/v1/admin/org/invite", json={"email": "invitee@x.com", "role": "viewer"},
        cookies=cookies, headers=headers).json()
    assert set(invite_body) == {"token"}

    accept_body = client.post(
        "/api/v1/admin/org/accept", json={"token": invite_body["token"]},
        cookies=auth_cookies("t", "owner", email="invitee@x.com", mfa=True)).json()
    assert set(accept_body) == {"role"}


def test_grant_and_remove_and_list_and_audit_shape(client):
    admin = _super_admin(client)
    cookies, headers = _with_csrf(admin)
    granted = client.put(
        "/api/v1/admin/org/granted-user@x.com", json={"role": "viewer"},
        cookies=cookies, headers=headers).json()
    assert set(granted) == {"email", "role", "capabilities"}

    listing = client.get("/api/v1/admin/org", cookies=admin).json()
    assert set(listing) == {"admins"}
    assert set(listing["admins"][0]) == {"email", "role", "capabilities"}

    role_of = client.get("/api/v1/admin/org/role/granted-user@x.com", cookies=admin).json()
    assert set(role_of) == {"email", "role"}

    removed = client.delete(
        "/api/v1/admin/org/granted-user@x.com", cookies=cookies, headers=headers).json()
    assert set(removed) == {"removed"}

    audit_body = client.get("/api/v1/admin/org/audit", cookies=admin).json()
    assert set(audit_body) == {"entries"}
    if audit_body["entries"]:
        assert set(audit_body["entries"][0]) == {
            "id", "email", "changed_by_email", "previous_role", "role",
            "previous_capabilities", "capabilities", "reason", "created_at",
        }
