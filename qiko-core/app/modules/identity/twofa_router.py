"""2FA (TOTP) enrollment API. Login already verifies TOTP inline (password + code); this adds the
enrollment: generate a secret + provisioning URI, then confirm a code to enable 2FA on the account.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import current_claims
from app.modules.identity import csrf, twofa
from app.modules.identity.onboarding import (
    exchange_temp_token,
    new_totp_secret,
    provisioning_uri,
    verify_totp,
)
from app.modules.identity.router import get_store
from app.modules.identity.security import hash_password, verify_password
from app.modules.identity.store import UserStore

router = APIRouter(prefix="/auth/2fa", tags=["identity"])


@router.post("/setup")
async def setup(request: Request, claims: dict = Depends(current_claims),
                store: UserStore = Depends(get_store)) -> dict:
    """Return a fresh TOTP secret + otpauth:// provisioning URI for the authenticator app.
    The secret is confirmed (and only then persisted) via /verify-setup."""
    csrf.require_csrf(request)
    user = await store.get_by_id(claims["sub"])
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.twofa_enabled:
        raise HTTPException(status_code=409, detail="2FA is already enabled")
    secret = new_totp_secret()
    return {"secret": secret, "provisioning_uri": provisioning_uri(secret, claims["sub"])}


class VerifyBody(BaseModel):
    secret: str = Field(min_length=1)
    code: str = Field(min_length=6, max_length=6)
    password: str = Field(min_length=1)
    current_code: str | None = Field(default=None, min_length=6, max_length=6)


@router.post("/verify-setup")
async def verify_setup(body: VerifyBody, request: Request,
                       claims: dict = Depends(current_claims),
                       store: UserStore = Depends(get_store)) -> dict:
    csrf.require_csrf(request)
    user = await store.get_by_id(claims["sub"])
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if user.twofa_enabled and not verify_totp(user.totp_secret or "", body.current_code or ""):
        raise HTTPException(status_code=401, detail="current 2FA code required")
    if not verify_totp(body.secret, body.code):
        raise HTTPException(status_code=400, detail="invalid code")
    backup_codes = twofa.new_backup_codes()
    backup_hashes = {twofa.backup_code_selector(code): hash_password(twofa.normalize_backup_code(code))
                     for code in backup_codes}
    await store.enable_twofa(claims["sub"], body.secret, backup_hashes)
    await store.set_sid(claims["sub"], None)
    return {"enabled": True, "reauthentication_required": True, "backup_codes": backup_codes}


class RegenerateBody(BaseModel):
    password: str = Field(min_length=1)
    current_code: str = Field(min_length=6, max_length=6)


@router.post("/backup-codes/regenerate")
async def regenerate_backup_codes(body: RegenerateBody, request: Request,
                                  claims: dict = Depends(current_claims),
                                  store: UserStore = Depends(get_store)) -> dict:
    csrf.require_csrf(request)
    if not claims.get("mfa"):
        raise HTTPException(status_code=403, detail="MFA session required")
    user = await store.get_by_id(claims["sub"])
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_totp(user.totp_secret or "", body.current_code):
        raise HTTPException(status_code=401, detail="current 2FA code required")
    backup_codes = twofa.new_backup_codes()
    backup_hashes = {twofa.backup_code_selector(code): hash_password(twofa.normalize_backup_code(code))
                     for code in backup_codes}
    await store.enable_twofa(user.id, user.totp_secret or "", backup_hashes)
    await store.set_sid(user.id, None)
    return {"backup_codes": backup_codes, "reauthentication_required": True}


class ExchangeBody(BaseModel):
    temp_token: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    code: str = Field(min_length=6, max_length=6)


@router.post("/exchange")
def exchange(body: ExchangeBody) -> dict:
    """Second step of the password -> temp-token -> 2FA login bridge; returns the verified user id."""
    try:
        return {"user_id": exchange_temp_token(body.temp_token, body.secret, body.code)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
