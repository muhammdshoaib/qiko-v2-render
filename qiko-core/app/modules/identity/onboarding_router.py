"""Signup bootstrap + OTP password reset (public identity flows)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import get_otp_store, get_teams
from app.modules.email.sender import get_email_sender
from app.modules.identity.onboarding import signup as bootstrap_signup
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.security import hash_password
from app.modules.identity.store import User, UserStore

router = APIRouter(prefix="/auth", tags=["identity"])


class SignupBody(BaseModel):
    tenant: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


@router.post("/signup")
async def signup(body: SignupBody, store: UserStore = Depends(get_store), teams=Depends(get_teams)) -> dict:
    rec = bootstrap_signup(teams, body.tenant, body.email, body.password, get_email_sender())
    uid = uuid.uuid4().hex[:12]
    await store.add(User(id=uid, email=rec["email"], password_hash=rec["password_hash"],
                         tenant=body.tenant, role=Role.owner))
    return {"user_id": uid, "email": rec["email"], "team_id": rec["team_id"]}


class ForgotBody(BaseModel):
    email: str = Field(min_length=3)


@router.post("/forgot-password")
def forgot_password(body: ForgotBody, otp=Depends(get_otp_store)) -> dict:
    code = otp.issue(body.email)
    get_email_sender().send(to=body.email, subject="Your Qiko reset code", body=f"Your code: {code}")
    resp = {"sent": True}
    # Dev convenience only. Gated on the environment, not just the email backend: if ops ever
    # leaves EMAIL_BACKEND=console in preprod/live (e.g. SMTP misconfigured), the OTP must never
    # leak into the HTTP response for a real, non-dev environment.
    settings = get_settings()
    if settings.debug and settings.email_backend == "console":
        resp["otp"] = code
    return resp


class ResetBody(BaseModel):
    email: str = Field(min_length=3)
    otp: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8)


@router.post("/reset-password")
async def reset_password(body: ResetBody, otp=Depends(get_otp_store), store: UserStore = Depends(get_store)) -> dict:
    if not otp.verify(body.email, body.otp):
        raise HTTPException(status_code=400, detail="invalid or expired code")
    user = await store.get_by_email(body.email)
    if user:
        await store.set_password(user.id, hash_password(body.new_password))
    return {"reset": True}
