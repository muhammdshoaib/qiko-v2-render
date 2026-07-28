"""2FA enrollment API: setup returns a secret + otpauth URI; verify-setup confirms a real code."""
import pyotp

from app.modules.identity.onboarding import new_totp_secret
from tests.helpers import auth_cookies

C = {**auth_cookies("tfa", "owner", user_id="u-owner"), "qiko_csrf": "csrf-test"}
H = {"x-csrf-token": "csrf-test", "origin": "http://testserver"}


def test_setup_returns_secret_and_uri(client):
    body = client.post("/api/v1/auth/2fa/setup", cookies=C, headers=H).json()
    assert len(body["secret"]) >= 16 and body["provisioning_uri"].startswith("otpauth://")


def test_verify_setup_rejects_wrong_code(client):
    secret = new_totp_secret()
    assert client.post("/api/v1/auth/2fa/verify-setup", json={"secret": secret, "code": "000000", "password": "change-me-locally"}, cookies=C, headers=H).status_code == 400


def test_verify_setup_with_real_code_enables(client):
    secret = client.post("/api/v1/auth/2fa/setup", cookies=C, headers=H).json()["secret"]
    code = pyotp.TOTP(secret).now()
    body = client.post("/api/v1/auth/2fa/verify-setup", json={"secret": secret, "code": code, "password": "change-me-locally"}, cookies=C, headers=H).json()
    assert body["enabled"] is True
    assert len(body["backup_codes"]) == 10 and len(set(body["backup_codes"])) == 10


def test_2fa_requires_auth(client):
    assert client.post("/api/v1/auth/2fa/setup").status_code == 401


def test_2fa_requires_csrf(client):
    assert client.post("/api/v1/auth/2fa/setup", cookies=auth_cookies("tfa", "owner")).status_code == 403


def test_2fa_rejects_cross_origin_outside_development(client, monkeypatch):
    from app.core.config import Environment, get_settings

    monkeypatch.setattr(get_settings(), "environment", Environment.live)
    monkeypatch.setattr(get_settings(), "cors_allow_origins", ["https://qiko.ai", "https://admin.qiko.ai"])
    response = client.post(
        "/api/v1/auth/2fa/setup", cookies=C,
        headers={**H, "origin": "https://evil.invalid"})
    assert response.status_code == 403
