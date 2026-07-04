"""2FA (TOTP) enrollment API. Login already verifies TOTP inline (password + code); this adds the
enrollment: generate a secret + provisioning URI, then confirm a code to enable 2FA on the account.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import current_claims
from app.modules.identity.onboarding import (
    exchange_temp_token,
    new_totp_secret,
    provisioning_uri,
    verify_totp,
)
from app.modules.identity.router import get_store
from app.modules.identity.store import UserStore

router = APIRouter(prefix="/auth/2fa", tags=["identity"])


@router.post("/setup")
def setup(claims: dict = Depends(current_claims)) -> dict:
    """Return a fresh TOTP secret + otpauth:// provisioning URI for the authenticator app.
    The secret is confirmed (and only then persisted) via /verify-setup."""
    secret = new_totp_secret()
    return {"secret": secret, "provisioning_uri": provisioning_uri(secret, claims["sub"])}


class VerifyBody(BaseModel):
    secret: str = Field(min_length=1)
    code: str = Field(min_length=6, max_length=6)


@router.post("/verify-setup")
async def verify_setup(body: VerifyBody, claims: dict = Depends(current_claims),
                       store: UserStore = Depends(get_store)) -> dict:
    if not verify_totp(body.secret, body.code):
        raise HTTPException(status_code=400, detail="invalid code")
    await store.enable_twofa(claims["sub"], body.secret)
    return {"enabled": True}


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
