"""Wave 5 of audit coverage: authentication.

There was no authentication trail of any kind. That is the single most commonly raised finding in a
SOC 2 CC6.1 sample: the auditor asks for successes AND failures and there is nothing to hand over.
Failures are the more useful half.
"""
import asyncio

from app.core.deps import get_user_store
from app.modules.audit import registry
from app.modules.identity.admin_rbac import AdminRole, Capability, default_capabilities
from app.modules.identity.rbac import Role
from app.modules.identity.security import hash_password
from app.modules.identity.store import User


def _user(email: str = "pilot@acme.invalid", password: str = "correct-horse-battery") -> None:
    asyncio.run(get_user_store().add(User(
        id="u-auth", email=email, password_hash=hash_password(password),
        tenant="authco", role=Role.owner, name="A Pilot")))


def _events(client, action: str) -> list[dict]:
    return [r for r in client.app.state.audit.rows if r["action"] == action]


def test_a_successful_login_is_recorded(client):
    _user()
    response = client.post("/api/v1/auth/login",
                           json={"email": "pilot@acme.invalid", "password": "correct-horse-battery"})
    assert response.status_code == 200

    row = _events(client, registry.LOGIN_SUCCEEDED)[0]
    assert row["target_label"] == "pilot@acme.invalid"
    assert row["tenant_id"] == "authco"
    assert row["event_metadata"]["mfa"] is False
    assert row["event_metadata"]["backup_code_used"] is False


def test_a_login_without_two_factor_does_not_raise(client):
    """used_backup_code was originally bound only inside the 2FA branch and read outside it, so every
    password-only login would have raised NameError after the audit was added."""
    _user()
    assert client.post("/api/v1/auth/login",
                       json={"email": "pilot@acme.invalid",
                             "password": "correct-horse-battery"}).status_code == 200


def test_the_failure_reason_separates_spraying_from_a_targeted_attack(client):
    """Many failures against unknown addresses is spraying; many against one known address is
    targeted. Collapsing both into "login failed" throws away the only signal worth having."""
    _user()
    client.post("/api/v1/auth/login", json={"email": "pilot@acme.invalid", "password": "wrong"})
    client.post("/api/v1/auth/login", json={"email": "nobody@acme.invalid", "password": "wrong"})

    reasons = [r["event_metadata"]["reason"] for r in _events(client, registry.LOGIN_FAILED)]
    assert reasons == ["bad_password", "unknown_account"]


def test_the_endpoint_stays_uniform_even_though_the_trail_is_not(client):
    """The distinction must live only in the audit. An endpoint that answers differently for a known
    and an unknown address is an account-existence oracle."""
    _user()
    known = client.post("/api/v1/auth/login",
                        json={"email": "pilot@acme.invalid", "password": "wrong"})
    unknown = client.post("/api/v1/auth/login",
                          json={"email": "nobody@acme.invalid", "password": "wrong"})
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_a_failed_second_factor_is_its_own_event(client):
    """The password was correct and only the second factor failed, so this is the event that says a
    credential is ALREADY compromised. It is not the same as a failed password."""
    from app.modules.identity import twofa

    secret = twofa.new_secret()
    asyncio.run(get_user_store().add(User(
        id="u-2fa", email="mfa@acme.invalid", password_hash=hash_password("correct-horse-battery"),
        tenant="authco", role=Role.owner, twofa_enabled=True, totp_secret=secret)))

    response = client.post("/api/v1/auth/login", json={
        "email": "mfa@acme.invalid", "password": "correct-horse-battery", "totp": "000000"})
    assert response.status_code == 401

    assert _events(client, registry.LOGIN_FAILED) == [], "the password was not the problem"
    row = _events(client, registry.MFA_FAILED)[0]
    assert row["target_label"] == "mfa@acme.invalid"
    assert row["event_metadata"]["reason"] == "invalid"


def test_no_password_or_secret_reaches_any_auth_row(client):
    _user(password="hunter2-is-a-terrible-password")
    client.post("/api/v1/auth/login",
                json={"email": "pilot@acme.invalid", "password": "hunter2-is-a-terrible-password"})
    client.post("/api/v1/auth/login",
                json={"email": "pilot@acme.invalid", "password": "another-wrong-one"})
    everything = str(client.app.state.audit.rows)
    assert "hunter2" not in everything
    assert "another-wrong-one" not in everything


def test_a_password_reset_is_recorded_including_against_an_unknown_address(client):
    """The endpoint deliberately returns success either way, so only this row distinguishes a typo
    from reconnaissance."""
    _user()
    login = client.post("/api/v1/auth/login", json={
        "email": "pilot@acme.invalid", "password": "correct-horse-battery"})
    assert login.status_code == 200
    user = asyncio.run(get_user_store().get_by_email("pilot@acme.invalid"))
    assert user is not None
    assert user.current_sid is not None

    otp = client.app.state.otp_store
    code = asyncio.run(otp.issue("pilot@acme.invalid"))
    response = client.post("/api/v1/auth/reset-password", json={
        "email": "pilot@acme.invalid", "otp": code, "new_password": "a-brand-new-password"})
    assert response.status_code == 200
    user = asyncio.run(get_user_store().get_by_email("pilot@acme.invalid"))
    assert user is not None
    assert user.current_sid is None

    row = _events(client, registry.PASSWORD_CHANGED)[0]
    assert row["changes"]["method"]["to"] == "reset_token"
    assert row["event_metadata"]["account_existed"] is True
    assert "a-brand-new-password" not in str(row)


def test_no_password_fingerprint_is_recorded():
    """Unlike an integration credential. A keyed truncated HMAC of a human-chosen password, across many
    users, is a correlation risk that buys nothing: nobody needs to know whether a password was reused,
    only that it changed and by which route."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "modules" / "identity" /
              "onboarding_router.py").read_text()
    # Parsed rather than grepped. A substring search over the file finds the docstring that explains
    # why there is no fingerprint, which is a test failing on its own justification.
    tree = ast.parse(source)
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    referenced |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    referenced |= {node.value for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)
                   and len(node.value) < 80}
    assert not any("fingerprint" in str(name).lower() for name in referenced), (
        "a password fingerprint reached the code")


# --- reading the trail is now its own privilege ---------------------------------------------------

def test_reading_the_audit_trail_needs_its_own_capability():
    """It used to sit on view_customers. That reasoning held while the trail contained admin actions;
    it stopped holding once authentication events landed here, because a failed-login trail tells a
    reader which accounts exist, when each colleague works and from which addresses."""
    assert Capability.view_audit not in default_capabilities(AdminRole.viewer)
    assert Capability.view_audit in default_capabilities(AdminRole.super_admin)


def test_a_customer_viewer_cannot_read_the_trail(client):
    from app.modules.identity import csrf
    from tests.helpers import auth_cookies, bootstrap_admin

    bootstrap_admin(client, "root@qiko.invalid")
    token = csrf.generate_csrf_token()
    root = {**auth_cookies("platform", "owner", email="root@qiko.invalid"), csrf.CSRF_COOKIE: token}
    client.put("/api/v1/admin/org/viewer@qiko.invalid", cookies=root,
               headers={csrf.CSRF_HEADER: token},
               json={"role": "viewer", "capabilities": [Capability.view_customers.value]})

    narrow = auth_cookies("platform", "viewer", email="viewer@qiko.invalid")
    assert client.get("/api/v1/admin/audit", cookies=narrow).status_code == 403
    assert client.get("/api/v1/admin/audit/actions", cookies=narrow).status_code == 403


def test_a_capability_denial_never_mentions_mfa(client):
    """The admin shell redirects to 2FA onboarding on any 403 whose body matches /mfa/i, so a
    capability denial that used the word would send an operator to enrol a second factor they already
    have."""
    from tests.helpers import auth_cookies

    response = client.get("/api/v1/admin/audit",
                          cookies=auth_cookies("platform", "viewer", email="nobody@qiko.invalid"))
    assert response.status_code == 403
    assert "mfa" not in response.text.lower()
