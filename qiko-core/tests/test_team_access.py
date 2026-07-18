"""Team Access API (Creator Settings > Team tab): list tenant users, invite, change role, remove,
plus RBAC and owner-protection guards. See app.modules.identity.users_router."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.security import hash_password
from app.modules.identity.store import InMemoryUserStore, User
from tests.helpers import auth_cookies

TENANT = "idg"


@pytest.fixture
def store() -> InMemoryUserStore:
    s = InMemoryUserStore()
    s.seed(User(id="u-owner", email="jake@qiko.ai", password_hash=hash_password("pw12345678"),
                tenant=TENANT, role=Role.owner))
    s.seed(User(id="u-creator", email="hussain@idg.com", password_hash=hash_password("pw12345678"),
                tenant=TENANT, role=Role.editor))
    s.seed(User(id="u-user", email="osama@idg.com", password_hash=hash_password("pw12345678"),
                tenant=TENANT, role=Role.viewer))
    # A user in a different tenant -- must never leak into idg's Team Access.
    s.seed(User(id="u-other", email="stranger@acme.com", password_hash=hash_password("pw12345678"),
                tenant="acme", role=Role.admin))
    return s


@pytest.fixture
def client(store) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


OWNER = auth_cookies(TENANT, "owner", user_id="u-owner", email="jake@qiko.ai")
VIEWER = auth_cookies(TENANT, "viewer", user_id="u-user", email="osama@idg.com")


def test_list_users_is_tenant_scoped(client):
    r = client.get("/api/v1/identity/users", cookies=OWNER)
    assert r.status_code == 200
    body = r.json()
    emails = {u["email"] for u in body["users"]}
    assert emails == {"jake@qiko.ai", "hussain@idg.com", "osama@idg.com"}
    assert "stranger@acme.com" not in emails  # cross-tenant isolation
    assert body["pending"] == []
    labels = {u["email"]: u["role_label"] for u in body["users"]}
    assert labels["jake@qiko.ai"] == "Owner"
    assert labels["hussain@idg.com"] == "Creator"
    assert labels["osama@idg.com"] == "User"


def test_invite_creates_pending(client):
    r = client.post("/api/v1/identity/users/invite",
                    json={"email": "New.Person@idg.com", "role": "admin"}, cookies=OWNER)
    assert r.status_code == 200
    assert r.json()["email"] == "new.person@idg.com"
    assert r.json()["role_label"] == "Admin"
    pending = client.get("/api/v1/identity/users", cookies=OWNER).json()["pending"]
    assert [p["email"] for p in pending] == ["new.person@idg.com"]


def test_invite_rejects_existing_and_owner_role(client):
    assert client.post("/api/v1/identity/users/invite",
                       json={"email": "hussain@idg.com", "role": "editor"}, cookies=OWNER).status_code == 409
    assert client.post("/api/v1/identity/users/invite",
                       json={"email": "brand-new@idg.com", "role": "owner"}, cookies=OWNER).status_code == 400


def test_cancel_pending_invite(client):
    client.post("/api/v1/identity/users/invite", json={"email": "temp@idg.com", "role": "viewer"}, cookies=OWNER)
    assert client.delete("/api/v1/identity/users/pending/temp@idg.com", cookies=OWNER).status_code == 200
    assert client.get("/api/v1/identity/users", cookies=OWNER).json()["pending"] == []
    assert client.delete("/api/v1/identity/users/pending/temp@idg.com", cookies=OWNER).status_code == 404


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


def test_rbac_viewer_cannot_mutate(client):
    assert client.get("/api/v1/identity/users", cookies=VIEWER).status_code == 200  # read is open
    assert client.post("/api/v1/identity/users/invite",
                       json={"email": "x@idg.com", "role": "viewer"}, cookies=VIEWER).status_code == 403
    assert client.put("/api/v1/identity/users/u-user/role",
                      json={"role": "editor"}, cookies=VIEWER).status_code == 403
    assert client.delete("/api/v1/identity/users/u-user", cookies=VIEWER).status_code == 403
