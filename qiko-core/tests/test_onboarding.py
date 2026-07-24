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
    assert "otpauth://" in provisioning_uri(secret, "a@x.com")
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
    otp = await store.issue("u@x.com")
    wrong = "000001" if otp != "000001" else "000002"
    assert await store.verify("u@x.com", wrong) is False   # wrong code
    assert await store.verify("u@x.com", otp) is True      # correct
    assert await store.verify("u@x.com", otp) is False    # single-use consumed
    assert await store.verify("u@x.com", await store.issue("u@x.com", ttl=-1)) is False  # expired


async def test_signup_bootstraps_team_owner_record():
    teams = TeamService()
    rec = await signup(teams, "acme", "Owner@X.com", "pw123456")
    assert rec["role"] == Role.owner.value and verify_password("pw123456", rec["password_hash"])
    assert (await teams.members(rec["team_id"]))["owner@x.com"] is Role.owner


def test_signup_endpoint_sends_branded_multipart_welcome_after_account_creation():
    app = create_app()
    mail = ConsoleEmailSender()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = lambda: mail
    app.dependency_overrides[get_settings] = lambda: Settings(
        public_base_url="https://preprod.qiko.ai",
    )
    client = TestClient(app)
    password = "correct-horse-battery-staple"

    response = client.post(
        "/api/v1/auth/signup",
        json={"tenant": "newco", "email": "Founder@X.com", "password": password},
    )

    assert response.status_code == 200
    assert set(response.json()) == {"user_id", "email", "team_id"}
    assert len(mail.sent) == 1
    sent = mail.sent[0]
    assert sent["to"] == "founder@x.com"
    assert "https://preprod.qiko.ai/login" in sent["body"]
    assert "https://preprod.qiko.ai/login" in sent["html"]
    assert sent["body"] and sent["html"]
    assert password not in str(sent)
    user = next(iter(store._by_id.values()))
    assert user.email == "founder@x.com"


def test_public_signup_cannot_join_a_caller_selected_tenant():
    app = create_app()
    mail = ConsoleEmailSender()
    store = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = lambda: mail
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/signup",
        json={"tenant": "idg", "email": "attacker@example.com", "password": "pw12345678"},
    )

    assert response.status_code == 200
    user = next(iter(store._by_id.values()))
    assert user.tenant != "idg"
    assert user.tenant.startswith("org-")
    assert user.role is Role.owner


def test_signup_sender_failure_is_safe_and_leaves_a_login_capable_account(caplog):
    secret = "smtp-password-should-not-leak"

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
        json={"tenant": "mailfail", "email": "mailfail@x.com", "password": "pw12345678"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "account created, but the welcome email could not be sent"}
    assert secret not in response.text
    assert secret not in caplog.text
    user = next(iter(store._by_id.values()))
    assert user.email == "mailfail@x.com" and verify_password("pw12345678", user.password_hash)


def test_forgot_password_sends_branded_multipart_email_from_public_url():
    app = create_app()
    mail = ConsoleEmailSender()
    store = InMemoryUserStore()
    store.seed(User(id="person", email="person@example.com", password_hash=hash_password("old-password"),
                    tenant="person-tenant", role=Role.owner))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = lambda: mail
    app.dependency_overrides[get_settings] = lambda: Settings(
        public_base_url="https://preprod.qiko.ai",
    )
    client = TestClient(app)

    response = client.post("/api/v1/auth/forgot-password", json={"email": "person@example.com"})

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

    response = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})

    assert response.status_code == 200 and response.json() == {"sent": True}
    assert mail.sent == []


def test_forgot_password_sender_failure_is_safe(caplog, capsys):
    secret = "smtp-reset-secret-should-not-leak"

    class FailingSender:
        def send(self, **_kwargs):
            raise RuntimeError(secret)

    app = create_app()
    store = InMemoryUserStore()
    store.seed(User(id="person", email="person@example.com", password_hash=hash_password("old-password"),
                    tenant="person-tenant", role=Role.owner))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = FailingSender
    client = TestClient(app)

    response = client.post("/api/v1/auth/forgot-password", json={"email": "person@example.com"})

    assert response.status_code == 200 and response.json()["sent"] is True
    captured = capsys.readouterr().err
    assert "transactional_email_failed" in captured
    assert secret not in response.text
    assert secret not in caplog.text + captured
