import pyotp
import pytest

from app.modules.email.sender import ConsoleEmailSender
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
from app.modules.identity.security import verify_password
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


async def test_signup_bootstraps_team_owner_and_welcome_email():
    teams, mail = TeamService(), ConsoleEmailSender()
    rec = await signup(teams, "acme", "Owner@X.com", "pw123456", mail)
    assert rec["role"] == Role.owner.value and verify_password("pw123456", rec["password_hash"])
    assert (await teams.members(rec["team_id"]))["owner@x.com"] is Role.owner
    assert mail.sent[0]["to"] == "owner@x.com" and "Qiko" in mail.sent[0]["subject"]
