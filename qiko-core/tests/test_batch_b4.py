import pyotp

from app.modules.identity.onboarding import issue_temp_token, new_totp_secret
from app.core.config import Environment, get_settings
from tests.helpers import auth_cookies

def _cookies():
    return auth_cookies("b4", "owner")


def test_teams_invites_and_member_mgmt(client):
    team = client.post("/api/v1/teams", json={"owner_id": "owner"}, cookies=_cookies()).json()
    tid = team["team_id"]
    tok = client.post(f"/api/v1/teams/{tid}/invites", json={"email": "new@invalid", "role": "editor"}, cookies=_cookies()).json()["token"]
    data = client.post("/api/v1/teams/invites/accept", json={"token": tok}, cookies=_cookies()).json()
    assert data["team_id"] == tid and data["email"] == "new@invalid"
    sp = client.post("/api/v1/teams/invites/set-password", json={"token": tok, "password": "s3cret-pw"}, cookies=_cookies()).json()
    assert sp["email"] == "new@invalid"
    client.post(f"/api/v1/teams/{tid}/members", json={"user_id": "u2", "role": "editor"}, cookies=_cookies())
    assert client.put(f"/api/v1/teams/{tid}/members/u2", json={"role": "admin"}, cookies=_cookies()).json()["members"]["u2"] == "admin"
    assert "u2" not in client.request("DELETE", f"/api/v1/teams/{tid}/members/u2", cookies=_cookies()).json()["members"]


def test_chat_files_conversations_clear(client):
    agent_id = client.post("/api/v1/agents", json={"name": "Chat"}, cookies=_cookies()).json()["id"]
    cid = client.post(
        "/api/v1/chat/conversations", json={"user_id": "u", "agent_id": agent_id}, cookies=_cookies()
    ).json()["conversation_id"]
    assert cid
    key = client.post("/api/v1/chat/files", json={"fmt": "xlsx", "filename": "report",
                      "spec": {"sheet": "S", "rows": [["a", "b"], [1, 2]]}}, cookies=_cookies()).json()["key"]
    dl = client.get(f"/api/v1/chat/files/{key}", cookies=_cookies())
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    assert client.delete("/api/v1/chat/history/x", cookies=_cookies()).json()["cleared"] is True


def test_signup_and_password_reset(client):
    su = client.post("/api/v1/auth/signup", json={"tenant": "newco", "email": "founder@invalid", "password": "pw12345678"}).json()
    assert su["user_id"] and su["team_id"]
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": "founder@invalid"}).json()
    assert forgot["sent"] is True
    otp = forgot["otp"]
    assert client.post("/api/v1/auth/reset-password", json={"email": "founder@invalid", "otp": otp, "new_password": "newpw12345"}).json()["reset"] is True


def test_2fa_exchange_bridge(client):
    secret = new_totp_secret()
    token = issue_temp_token("u-1")
    r = client.post("/api/v1/auth/2fa/exchange", json={"temp_token": token, "secret": secret, "code": pyotp.TOTP(secret).now()})
    assert r.json()["user_id"] == "u-1"
    assert client.post("/api/v1/auth/2fa/exchange", json={"temp_token": token, "secret": secret, "code": "000000"}).status_code == 400


def test_admin_bootstrap_is_disabled_outside_dev(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", Environment.preprod)
    caller = auth_cookies("public", "owner", email="public-owner@invalid")

    assert client.post("/api/v1/admin/org/bootstrap", cookies=caller).status_code == 404
    assert client.post("/api/v1/admin/org/invite",
                       json={"email": "admin@invalid", "role": "viewer"}, cookies=caller).status_code == 404
    assert client.post("/api/v1/admin/org/accept", json={"token": "anything"}).status_code == 404


def test_admin_org_rbac(client):
    boss = auth_cookies("b4", "owner", email="boss@invalid")
    assert client.post("/api/v1/admin/org/bootstrap", cookies=boss).json()["super_admin"] == "boss@invalid"
    # bootstrap is first-run only -- a second caller can't self-escalate afterwards
    other = auth_cookies("b4", "owner", email="other@invalid")
    assert client.post("/api/v1/admin/org/bootstrap", cookies=other).status_code == 409
    tok = client.post("/api/v1/admin/org/invite", json={"email": "viewer@invalid", "role": "viewer"}, cookies=boss).json()["token"]
    assert client.post("/api/v1/admin/org/accept", json={"token": tok}, cookies=boss).json()["role"] == "viewer"
    assert client.get("/api/v1/admin/org/role/viewer@invalid", cookies=boss).json()["role"] == "viewer"
