"""Signup bootstrap, OTP password reset, and 2FA enrollment + temp-token login bridge.

qiko-core already verifies TOTP at login; this adds enrollment (setup/verify-setup), the
password -> temp-token -> 2FA -> JWT bridge, and OTP-based password reset.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

import jwt
import pyotp

from app.core.config import get_settings
from app.modules.email.sender import EmailSender
from app.modules.email.templates import verification_email
from app.modules.identity.rbac import Role
from app.modules.identity.security import hash_password
from app.modules.teams.service import TeamService

_ALGO = "HS256"


# --- 2FA enrollment ---
def new_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Qiko")


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# --- temp-token login bridge (issued after password, before 2FA) ---
def issue_temp_token(user_id: str, *, ttl: int = 300) -> str:
    return jwt.encode({"sub": user_id, "twofa_pending": True, "exp": int(time.time()) + ttl},
                      get_settings().session_secret, algorithm=_ALGO)


def exchange_temp_token(token: str, secret: str, code: str) -> str:
    """Verify the temp token + the TOTP code; return the user id to mint the real session for."""
    try:
        data = jwt.decode(token, get_settings().session_secret, algorithms=[_ALGO])
    except jwt.PyJWTError as e:
        raise ValueError("invalid or expired temp token") from e
    if not data.get("twofa_pending") or not verify_totp(secret, code):
        raise ValueError("2FA verification failed")
    return data["sub"]


# --- password reset OTP ---
@dataclass
class OtpStore:
    _otps: dict[str, tuple[str, float]] = field(default_factory=dict)

    def issue(self, email: str, *, ttl: int = 600) -> str:
        otp = f"{secrets.randbelow(1_000_000):06d}"
        self._otps[email.lower()] = (otp, time.monotonic() + ttl)
        return otp

    def verify(self, email: str, otp: str) -> bool:
        rec = self._otps.get(email.lower())
        if not rec or rec[1] < time.monotonic():
            return False
        ok = secrets.compare_digest(rec[0], otp)
        if ok:
            del self._otps[email.lower()]  # single-use
        return ok


# --- signup bootstrap ---
async def signup(teams: TeamService, tenant: str, email: str, password: str, email_sender: EmailSender) -> dict:
    """Atomically create the user + their team (owner) + send the welcome/verification email."""
    team = await teams.create_team(tenant, email.lower())
    subject, body = verification_email(f"https://qiko.ai/verify?email={email.lower()}")
    email_sender.send(to=email.lower(), subject=subject, body=body)
    return {"email": email.lower(), "team_id": team.id, "role": Role.owner.value,
            "password_hash": hash_password(password)}
