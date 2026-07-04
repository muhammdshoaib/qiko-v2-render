import pyotp
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store, require_role
from app.modules.identity.security import hash_password
from app.modules.identity.store import InMemoryUserStore, User


@pytest.fixture
def store() -> InMemoryUserStore:
    s = InMemoryUserStore()
    s.seed(User(id="u1", email="owner@qiko.ai", password_hash=hash_password("pw12345"),
                tenant="acme", role=Role.owner))
    return s


@pytest.fixture
def client(store) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


def _login(client, email="owner@qiko.ai", password="pw12345", **kw):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password, **kw})


def test_login_sets_cookies_and_me_works(client):
    r = _login(client)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "owner@qiko.ai"
    assert "qiko_access" in client.cookies and "qiko_csrf" in client.cookies
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["user"]["role"] == "owner"


def test_login_wrong_password(client):
    assert _login(client, password="nope").status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_refresh_requires_csrf_then_rotates(client):
    _login(client)
    # without CSRF header -> 403
    assert client.post("/api/v1/auth/refresh").status_code == 403
    # with CSRF header from the cookie -> 200
    token = client.cookies["qiko_csrf"]
    assert client.post("/api/v1/auth/refresh", headers={"x-csrf-token": token}).status_code == 200


def test_logout_clears_session(client):
    _login(client)
    token = client.cookies["qiko_csrf"]
    assert client.post("/api/v1/auth/logout", headers={"x-csrf-token": token}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_single_session_revocation(client, store):
    _login(client)
    assert client.get("/api/v1/auth/me").status_code == 200
    store._by_id["u1"].current_sid = "some-other-session"  # simulate login elsewhere
    assert client.get("/api/v1/auth/me").status_code == 401


def test_twofa_enforced(store):
    secret = pyotp.random_base32()
    store.seed(User(id="u2", email="2fa@qiko.ai", password_hash=hash_password("pw12345"),
                    role=Role.editor, twofa_enabled=True, totp_secret=secret))
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"email": "2fa@qiko.ai", "password": "pw12345"}).status_code == 401
    code = pyotp.TOTP(secret).now()
    assert c.post("/api/v1/auth/login",
                  json={"email": "2fa@qiko.ai", "password": "pw12345", "totp": code}).status_code == 200


def test_require_role_guard():
    owner = User(id="o", email="o@x.io", password_hash="x", role=Role.owner)
    viewer = User(id="v", email="v@x.io", password_hash="x", role=Role.viewer)
    assert require_role(Role.admin)(user=owner) is owner
    with pytest.raises(HTTPException):
        require_role(Role.admin)(user=viewer)
