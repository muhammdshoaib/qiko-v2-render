"""2FA enrollment API: setup returns a secret + otpauth URI; verify-setup confirms a real code."""
import pyotp

from tests.helpers import auth_cookies

C = auth_cookies("tfa", "owner", user_id="u-owner")


def test_setup_returns_secret_and_uri(client):
    body = client.post("/api/v1/auth/2fa/setup", cookies=C).json()
    assert len(body["secret"]) >= 16 and body["provisioning_uri"].startswith("otpauth://")


def test_verify_setup_with_real_code_enables(client):
    secret = client.post("/api/v1/auth/2fa/setup", cookies=C).json()["secret"]
    code = pyotp.TOTP(secret).now()
    assert client.post("/api/v1/auth/2fa/verify-setup", json={"secret": secret, "code": code}, cookies=C).json()["enabled"] is True


def test_verify_setup_rejects_wrong_code(client):
    secret = client.post("/api/v1/auth/2fa/setup", cookies=C).json()["secret"]
    assert client.post("/api/v1/auth/2fa/verify-setup", json={"secret": secret, "code": "000000"}, cookies=C).status_code == 400


def test_2fa_requires_auth(client):
    assert client.post("/api/v1/auth/2fa/setup").status_code == 401
