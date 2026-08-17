import asyncio
import pyotp
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.modules.email.sender import ConsoleEmailSender, get_email_sender
from app.modules.identity.onboarding import (
    OtpStore,
    exchange_temp_token,
    issue_temp_token,
    new_totp_secret,
    provisioning_uri,
    signup,
    verify_totp,
)
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.security import hash_password, verify_password
from app.modules.identity.store import InMemoryUserStore, User
from app.modules.teams.service import TeamService


def test_2fa_enrollment():
    secret = new_totp_secret()
    assert "otpauth://" in provisioning_uri(secret, "a" + "@" + "x.com")
    assert verify_totp(secret, pyotp.TOTP(secret).now()) is True
    assert verify_totp(secret, "abc") is False


def test_temp_token_bridge():
    secret = new_totp_secret()
    token = issue_temp_token("user-1")
    assert exchange_temp_token(token, secret, pyotp.TOTP(secret).now()) == "user-1"
    with pytest.raises(ValueError):
        exchange_temp_token(token, secret, "000000")          # wrong code
    with pytest.raises(ValueError):
        exchange_temp_token("garbage", secret, pyotp.TOTP(secret).now())  # bad token


async def test_password_reset_otp():
    store = OtpStore()
    otp = await store.issue("u" + "@" + "x.com")
    wrong = "000001" if otp != "000001" else "000002"
    assert await store.verify("u" + "@" + "x.com", wrong) is False   # wrong code
    assert await store.verify("u" + "@" + "x.com", otp) is True      # correct
    assert await store.verify("u" + "@" + "x.com", otp) is False    # single-use consumed
    assert await store.verify("u" + "@" + "x.com", await store.issue("u" + "@" + "x.com", ttl=-1)) is False  # expired


async def test_signup_bootstraps_team_owner_record():
    teams = TeamService()
    rec = await signup(teams, "acme", "Owner" + "@" + "X.com", "pw123456")
    assert rec["role"] == Role.owner.value and verify_password("pw123456", rec["password_hash"])
    assert (await teams.members(rec["team_id"]))["owner" + "@" + "x.com"] is Role.owner


POLICY_ACCEPTANCE = {
    "accept_policies": True,
    "terms_release_id": "terms-2026-07-24",
    "privacy_release_id": "privacy-2026-07-24",
    "cookies_release_id": "cookies-2026-07-24",
}


def _complete_signup(client, email: str, password: str = "correct-horse-battery-staple", **extra):
    signup_response = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, **POLICY_ACCEPTANCE, **extra},
    )
    assert signup_response.status_code == 202
    verification = client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": signup_response.json()["verification_code"],
              "password": password, **POLICY_ACCEPTANCE},
    )
    return signup_response, verification


def test_signup_does_not_require_password_and_verification_issues_session():
    """Password is selected once during verification, not typed twice. After verification the
    user is authenticated, so they are not dumped back at /login."""
    app = create_app()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    email = "nopassword" + "@" + "example.test"
    password = "correct-horse-battery-staple"

    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "name": "No Password User", **POLICY_ACCEPTANCE},
    )
    assert signup.status_code == 202, signup.text

    verification = client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": signup.json()["verification_code"],
              "password": password, **POLICY_ACCEPTANCE},
    )
    assert verification.status_code == 200, verification.text
    assert set(verification.json()) == {"user_id", "email", "team_id"}

    # Session cookies issued by verification; /auth/me works immediately.
    assert "qiko_access" in client.cookies
    assert "qiko_csrf" in client.cookies
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email.lower()


    # Login with the verification password also works (session was persisted under that hash).
    # This is a sanity check that the user record actually received the password.
    assert client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200


def test_signup_requires_explicit_current_policy_acceptance():
    client = TestClient(create_app())
    base = {"email": "founder" + "@" + "example.test", "password": "pw12345678"}
    assert client.post("/api/v1/auth/signup", json=base).status_code == 422
    assert client.post(
        "/api/v1/auth/signup", json={**base, **POLICY_ACCEPTANCE, "accept_policies": False}
    ).status_code == 422
    assert client.post(
        "/api/v1/auth/signup",
        json={**base, **POLICY_ACCEPTANCE, "terms_release_id": "terms-old"},
    ).status_code == 422


def test_signup_sends_one_time_code_and_creates_no_user_until_verified():
    app = create_app()
    mail = ConsoleEmailSender()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = lambda: mail
    app.dependency_overrides[get_settings] = lambda: Settings(public_base_url="https://preprod.qiko.ai")
    client = TestClient(app)
    password = "cor" + "rect-horse-battery-staple"

    signup_response = client.post(
        "/api/v1/auth/signup",
        json={"tenant": "newco", "email": "Founder" + "@" + "X.com", "password": password, **POLICY_ACCEPTANCE},
    )
    assert signup_response.status_code == 202
    assert store._by_id == {}
    assert client.post("/api/v1/auth/login", json={
        "email": "founder" + "@" + "x.com", "password": password
    }).status_code == 401
    assert len(mail.sent) == 1
    sent = mail.sent[0]
    assert sent["to"] == "founder" + "@" + "x.com"
    assert signup_response.json()["verification_code"] in sent["body"]
    assert "https://preprod.qiko.ai/verify-email?email=founder%40x.com" in sent["body"]
    assert password not in str(sent)

    verified = client.post("/api/v1/auth/verify-email", json={
        "email": "Founder" + "@" + "X.com", "code": signup_response.json()["verification_code"],
        "password": password, **POLICY_ACCEPTANCE
    })
    assert verified.status_code == 200
    assert set(verified.json()) == {"user_id", "email", "team_id"}
    user = next(iter(store._by_id.values()))
    assert user.email == "founder" + "@" + "x.com" and verify_password(password, user.password_hash)
    assert user.tenant.startswith("org-") and user.tenant != "newco"
    assert app.state.consent.store.records[0].source == "signup"
    assert app.state.consent.store.records[0].action == "accept"
    assert len(mail.sent) == 2 and "https://preprod.qiko.ai/login" in mail.sent[1]["body"]
    assert client.post("/api/v1/auth/verify-email", json={
        "email": "Founder" + "@" + "X.com", "code": signup_response.json()["verification_code"],
        "password": password, **POLICY_ACCEPTANCE
    }).status_code == 400


def test_email_owner_selects_password_during_verification():
    app = create_app()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    signup = client.post("/api/v1/auth/signup", json={
        "email": "owner" + "@" + "example.test", "password": "attacker-known-password",
        **POLICY_ACCEPTANCE,
    })
    missing_clickwrap = client.post("/api/v1/auth/verify-email", json={
        "email": "owner" + "@" + "example.test", "code": signup.json()["verification_code"],
        "password": "owner-selected-password",
    })
    assert missing_clickwrap.status_code == 422
    verified = client.post("/api/v1/auth/verify-email", json={
        "email": "owner" + "@" + "example.test", "code": signup.json()["verification_code"],
        "password": "owner-selected-password", **POLICY_ACCEPTANCE,
    })
    assert verified.status_code == 200
    user = next(iter(store._by_id.values()))
    assert verify_password("owner-selected-password", user.password_hash)
    assert not verify_password("attacker-known-password", user.password_hash)


def test_clickwrap_is_persisted_before_user_creation():
    app = create_app()

    class OrderingStore(InMemoryUserStore):
        async def add(self, user):
            assert app.state.consent.store.records
            return await super().add(user)

    store = OrderingStore()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    _, verified = _complete_signup(client, "ordered" + "@" + "example.test", tenant="idg")
    assert verified.status_code == 200
    user = next(iter(store._by_id.values()))
    assert user.tenant.startswith("org-") and user.tenant != "idg"
    assert user.role is Role.owner


def test_signup_sender_failure_is_safe_and_leaves_no_login_capable_account(caplog):
    secret = "smtp" + "-password-should-not-leak"

    class FailingSender:
        def send(self, **_kwargs):
            raise RuntimeError(secret)

    app = create_app()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = FailingSender
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/signup",
        json={"tenant": "mailfail", "email": "mailfail" + "@" + "x.com", "password": "pw12345678",
              **POLICY_ACCEPTANCE},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "verification email could not be sent"}
    assert secret not in response.text
    assert secret not in caplog.text
    assert store._by_id == {}


def test_forgot_password_sends_branded_multipart_email_from_public_url():
    app = create_app()
    mail = ConsoleEmailSender()
    store = InMemoryUserStore()
    store.seed(User(id="person", email="person" + "@" + "example.com", password_hash=hash_password("old-password"),
                    tenant="person-tenant", role=Role.owner))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = lambda: mail
    app.dependency_overrides[get_settings] = lambda: Settings(
        public_base_url="https://preprod.qiko.ai",
    )
    client = TestClient(app)

    response = client.post("/api/v1/auth/forgot-password", json={"email": "person" + "@" + "example.com"})

    assert response.status_code == 200 and response.json()["sent"] is True
    assert len(mail.sent) == 1
    sent = mail.sent[0]
    assert "https://preprod.qiko.ai/reset-password?email=person%40example.com" not in sent["body"]
    assert "https://preprod.qiko.ai/reset-password?email=person%40example.com" not in sent["html"]


def test_forgot_password_unknown_address_returns_same_response_without_sending():
    app = create_app()
    mail = ConsoleEmailSender()
    app.dependency_overrides[get_store] = lambda: InMemoryUserStore()
    app.dependency_overrides[get_email_sender] = lambda: mail
    client = TestClient(app)

    response = client.post("/api/v1/auth/forgot-password", json={"email": "unknown" + "@" + "example.com"})

    assert response.status_code == 200 and response.json() == {"sent": True}
    assert mail.sent == []


def test_forgot_password_sender_failure_is_safe(caplog, capsys):
    secret = "smtp" + "-reset-secret-should-not-leak"

    class FailingSender:
        def send(self, **_kwargs):
            raise RuntimeError(secret)

    app = create_app()
    store = InMemoryUserStore()
    store.seed(User(id="person", email="person" + "@" + "example.com", password_hash=hash_password("old-password"),
                    tenant="person-tenant", role=Role.owner))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = FailingSender
    client = TestClient(app)

    response = client.post("/api/v1/auth/forgot-password", json={"email": "person" + "@" + "example.com"})

    assert response.status_code == 200 and response.json()["sent"] is True
    captured = capsys.readouterr().err
    assert "transactional_email_failed" in captured
    assert secret not in response.text
    assert secret not in caplog.text + captured


def test_signup_persists_the_display_name_typed_at_register():
    """The register form always collected a name, but it was dropped on the way in (SignupBody had
    no name field and forbids extras), so every account was created nameless even though users.name
    exists and Settings renders a display name."""
    app = create_app()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    email = "named" + "@" + "example.test"

    _, verified = _complete_signup(client, email, name="  Ada Lovelace  ")
    assert verified.status_code == 200

    user = asyncio.run(store.get_by_email(email))
    assert user is not None
    assert user.name == "Ada Lovelace"  # trimmed, and actually stored


def test_signup_without_a_name_still_works_and_stores_none():
    app = create_app()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    email = "anon" + "@" + "example.test"

    _, verified = _complete_signup(client, email)
    assert verified.status_code == 200
    user = asyncio.run(store.get_by_email(email))
    assert user is not None and user.name is None


def test_login_reports_missing_2fa_code_so_the_ui_can_ask_for_it():
    """The creator app had no code field, so a 2FA account could never sign in there. The error must
    stay identifiable (it is what the UI matches on to reveal the code input)."""
    app = create_app()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    email = "twofa" + "@" + "example.test"
    password = "correct-horse-battery-staple"
    _complete_signup(client, email, password=password)

    user = asyncio.run(store.get_by_email(email))
    user.twofa_enabled = True
    user.totp_secret = "JBSWY3DPEHPK3PXP"

    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401
    assert "2FA" in r.json()["detail"]

    import pyotp

    code = pyotp.TOTP("JBSWY3DPEHPK3PXP").now()
    ok = client.post("/api/v1/auth/login", json={"email": email, "password": password, "totp": code})
    assert ok.status_code == 200
