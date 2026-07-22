"""Team Access API (Creator Settings > Team tab): list tenant users, invite, change role, remove,
plus RBAC and owner-protection guards. See app.modules.identity.users_router."""
import re
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.modules.email.sender import ConsoleEmailSender, get_email_sender
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.security import hash_password
from app.modules.identity.store import InMemoryUserStore, User
from app.modules.identity.users_router import _display_name
from tests.helpers import auth_cookies

TENANT = "idg"


@pytest.fixture
def store() -> InMemoryUserStore:
    s = InMemoryUserStore()
    s.seed(User(id="u-owner", email="owner@example.com", password_hash=hash_password("pw12345678"),
                tenant=TENANT, role=Role.owner))
    s.seed(User(id="u-creator", email="creator@example.test", password_hash=hash_password("pw12345678"),
                tenant=TENANT, role=Role.editor))
    s.seed(User(id="u-user", email="viewer@example.test", password_hash=hash_password("pw12345678"),
                tenant=TENANT, role=Role.viewer))
    # A user in a different tenant -- must never leak into idg's Team Access.
    s.seed(User(id="u-other", email="stranger@example.net", password_hash=hash_password("pw12345678"),
                tenant="acme", role=Role.admin))
    return s


@pytest.fixture
def mail() -> ConsoleEmailSender:
    return ConsoleEmailSender()


@pytest.fixture
def client(store, mail) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_email_sender] = lambda: mail
    app.dependency_overrides[get_settings] = lambda: Settings(
        public_base_url="https://app.qiko.ai",
    )
    return TestClient(app)


OWNER = auth_cookies(TENANT, "owner", user_id="u-owner", email="owner@example.com")
VIEWER = auth_cookies(TENANT, "viewer", user_id="u-user", email="viewer@example.test")


def test_list_users_is_tenant_scoped(client):
    r = client.get("/api/v1/identity/users", cookies=OWNER)
    assert r.status_code == 200
    body = r.json()
    emails = {u["email"] for u in body["users"]}
    assert emails == {"owner@example.com", "creator@example.test", "viewer@example.test"}
    assert "stranger@example.net" not in emails  # cross-tenant isolation
    assert body["pending"] == []
    labels = {u["email"]: u["role_label"] for u in body["users"]}
    assert labels["owner@example.com"] == "Owner"
    assert labels["creator@example.test"] == "Creator"
    assert labels["viewer@example.test"] == "User"


def test_invite_creates_pending_and_sends_one_branded_multipart_email(client, mail):
    r = client.post("/api/v1/identity/users/invite",
                    json={"email": "New.Person@example.test", "role": "admin"}, cookies=OWNER)
    assert r.status_code == 200
    assert r.json()["email"] == "new.person@example.test"
    assert r.json()["role_label"] == "Admin"
    pending = client.get("/api/v1/identity/users", cookies=OWNER).json()["pending"]
    assert [p["email"] for p in pending] == ["new.person@example.test"]

    assert len(mail.sent) == 1
    sent = mail.sent[0]
    assert sent["to"] == "new.person@example.test"
    assert sent["body"] and sent["html"]
    assert "https://app.qiko.ai/signup" in sent["body"]
    assert "https://app.qiko.ai/signup" in sent["html"]
    assert "idg" in sent["body"] and "owner@example.com" in sent["body"]
    assert "same email address" in sent["body"]


def test_invited_signup_consumes_signed_invite_and_applies_tenant_role(client, store, mail):
    invite = client.post(
        "/api/v1/identity/users/invite",
        json={"email": "invited@example.test", "role": "editor"},
        cookies=OWNER,
    )
    assert invite.status_code == 200
    signup_link = re.search(r"https://app\.qiko\.ai/signup\?\S+", mail.sent[0]["body"]).group(0)
    token = parse_qs(urlparse(signup_link).query)["invite"][0]

    signup = client.post(
        "/api/v1/auth/signup",
        json={"tenant": "attacker-selected", "email": "invited@example.test",
              "password": "pw12345678", "invite_token": token},
    )

    assert signup.status_code == 200
    user = next(user for user in store._by_id.values() if user.email == "invited@example.test")
    assert user.tenant == TENANT and user.role is Role.editor
    assert client.get("/api/v1/identity/users", cookies=OWNER).json()["pending"] == []
    replay = client.post(
        "/api/v1/auth/signup",
        json={"email": "invited@example.test", "password": "different-password", "invite_token": token},
    )
    assert replay.status_code == 400


def test_cancelled_invite_token_cannot_authorise_a_later_reinvite(client, store, mail):
    payload = {"email": "reinvite@example.test", "role": "viewer"}
    assert client.post("/api/v1/identity/users/invite", json=payload, cookies=OWNER).status_code == 200
    old_link = re.search(r"https://app\.qiko\.ai/signup\?\S+", mail.sent[-1]["body"]).group(0)
    old_token = parse_qs(urlparse(old_link).query)["invite"][0]
    assert client.delete("/api/v1/identity/users/pending/reinvite@example.test", cookies=OWNER).status_code == 200
    assert client.post("/api/v1/identity/users/invite", json=payload, cookies=OWNER).status_code == 200

    old_signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "reinvite@example.test", "password": "pw12345678", "invite_token": old_token},
    )
    assert old_signup.status_code == 400
    assert all(user.email != "reinvite@example.test" for user in store._by_id.values())


def test_invite_rejects_existing_and_owner_role_without_sending(client, mail):
    assert client.post("/api/v1/identity/users/invite",
                       json={"email": "creator@example.test", "role": "editor"}, cookies=OWNER).status_code == 409
    assert client.post("/api/v1/identity/users/invite",
                       json={"email": "stranger@example.net", "role": "viewer"}, cookies=OWNER).status_code == 409
    assert client.post("/api/v1/identity/users/invite",
                       json={"email": "brand-new@example.test", "role": "owner"}, cookies=OWNER).status_code == 400
    assert mail.sent == []


def test_duplicate_pending_invite_is_a_no_op_and_does_not_send_again(client, mail):
    payload = {"email": "duplicate@example.test", "role": "viewer"}
    assert client.post("/api/v1/identity/users/invite", json=payload, cookies=OWNER).status_code == 200
    duplicate = client.post("/api/v1/identity/users/invite", json=payload, cookies=OWNER)

    assert duplicate.status_code == 409
    assert len(mail.sent) == 1
    pending = client.get("/api/v1/identity/users", cookies=OWNER).json()["pending"]
    assert [p["email"] for p in pending] == ["duplicate@example.test"]


def test_cancel_pending_invite_does_not_send_an_email(client, mail):
    client.post("/api/v1/identity/users/invite", json={"email": "temp@example.test", "role": "viewer"}, cookies=OWNER)
    assert len(mail.sent) == 1
    assert client.delete("/api/v1/identity/users/pending/temp@example.test", cookies=OWNER).status_code == 200
    assert len(mail.sent) == 1
    assert client.get("/api/v1/identity/users", cookies=OWNER).json()["pending"] == []
    assert client.delete("/api/v1/identity/users/pending/temp@example.test", cookies=OWNER).status_code == 404
    assert len(mail.sent) == 1


def test_invite_sender_failure_returns_safe_error_and_rolls_back_pending(client, caplog):
    secret = "smtp-password-should-not-leak"

    class FailingSender:
        def send(self, **_kwargs):
            raise RuntimeError(secret)

    client.app.dependency_overrides[get_email_sender] = FailingSender
    response = client.post(
        "/api/v1/identity/users/invite",
        json={"email": "retry@example.test", "role": "viewer"},
        cookies=OWNER,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "invitation email could not be sent; please try again"}
    assert secret not in response.text
    assert secret not in caplog.text
    assert client.get("/api/v1/identity/users", cookies=OWNER).json()["pending"] == []


def test_update_role(client, store):
    r = client.put("/api/v1/identity/users/u-user/role", json={"role": "editor"}, cookies=OWNER)
    assert r.status_code == 200 and r.json()["role_label"] == "Creator"
    assert store._by_id["u-user"].role is Role.editor


def test_update_role_owner_protected(client):
    assert client.put("/api/v1/identity/users/u-owner/role",
                      json={"role": "viewer"}, cookies=OWNER).status_code == 400


def test_update_role_rejects_owner_assignment(client):
    assert client.put("/api/v1/identity/users/u-creator/role",
                      json={"role": "owner"}, cookies=OWNER).status_code == 400


def test_remove_user(client, store):
    r = client.delete("/api/v1/identity/users/u-user", cookies=OWNER)
    assert r.status_code == 200 and r.json()["removed"] == "u-user"
    assert "u-user" not in store._by_id


def test_remove_owner_protected(client):
    assert client.delete("/api/v1/identity/users/u-owner", cookies=OWNER).status_code == 400


def test_cross_tenant_target_is_404(client):
    assert client.put("/api/v1/identity/users/u-other/role",
                      json={"role": "viewer"}, cookies=OWNER).status_code == 404
    assert client.delete("/api/v1/identity/users/u-other", cookies=OWNER).status_code == 404


def test_display_name_humanises_email_local_part():
    u = User(id="u-x", email="ronan.bolger@x.com", password_hash="h", tenant=TENANT, role=Role.viewer)
    assert _display_name(u) == "Ronan Bolger"
    # underscores and hyphens are treated as separators too
    assert _display_name(User(id="u-y", email="mary-jane_watson@x.com", password_hash="h",
                             tenant=TENANT, role=Role.viewer)) == "Mary Jane Watson"
    # falls back to id when there is no email
    assert _display_name(User(id="u-z", email="", password_hash="h",
                             tenant=TENANT, role=Role.viewer)) == "u-z"


def test_rbac_viewer_cannot_mutate(client):
    assert client.get("/api/v1/identity/users", cookies=VIEWER).status_code == 200  # read is open
    assert client.post("/api/v1/identity/users/invite",
                       json={"email": "x@example.test", "role": "viewer"}, cookies=VIEWER).status_code == 403
    assert client.put("/api/v1/identity/users/u-user/role",
                      json={"role": "editor"}, cookies=VIEWER).status_code == 403
    assert client.delete("/api/v1/identity/users/u-user", cookies=VIEWER).status_code == 403
