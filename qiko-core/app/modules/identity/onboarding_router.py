"""Signup bootstrap + OTP password reset (public identity flows)."""
from __future__ import annotations

import logging
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.deps import get_otp_store, get_pending_invites, get_teams
from app.modules.email.sender import EmailSender, get_email_sender
from app.modules.email.templates import password_reset_code_email, welcome_email
from app.modules.identity.onboarding import signup as bootstrap_signup
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.security import hash_password
from app.modules.identity.store import User, UserStore
from app.modules.identity.team_access import ASSIGNABLE_ROLES, PendingInviteStore
from app.modules.identity.tokens import TokenError, decode_token

router = APIRouter(prefix="/auth", tags=["identity"])
logger = logging.getLogger(__name__)


class SignupBody(BaseModel):
    # `tenant` remains accepted for backwards-compatible clients but is never trusted. Public signup
    # receives a server-generated tenant; invited signup derives membership from a signed token.
    tenant: str | None = None
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    invite_token: str | None = None


@router.post("/signup")
async def signup(
    body: SignupBody,
    store: UserStore = Depends(get_store),
    teams=Depends(get_teams),
    pending: PendingInviteStore = Depends(get_pending_invites),
    email_sender: EmailSender = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> dict:
    email = body.email.strip().lower()
    uid = uuid.uuid4().hex[:12]
    team_id: str | None = None
    if body.invite_token:
        try:
            claims = decode_token(body.invite_token, expected_type="team_invite")
            tenant = str(claims["tenant"])
            invited_email = str(claims["email"]).lower()
            role = Role(str(claims["role"]))
            invite_version = int(claims["invite_version"])
        except (KeyError, TypeError, ValueError, TokenError) as exc:
            raise HTTPException(status_code=400, detail="invalid or expired invitation") from exc
        if email != invited_email or role not in ASSIGNABLE_ROLES:
            raise HTTPException(status_code=400, detail="invitation does not match this account")
        invite = await pending.get(tenant, email)
        if (invite is None or invite.role != role
                or int(invite.invited_at * 1_000_000) != invite_version):
            raise HTTPException(status_code=400, detail="invitation is no longer pending")
        if await store.get_by_email(email) is not None:
            raise HTTPException(status_code=409, detail="an account with that email already exists")
        await store.add(User(id=uid, email=email, password_hash=hash_password(body.password),
                             tenant=tenant, role=role))
        await pending.remove(tenant, email)
        rec = {"email": email}
    else:
        # A public caller must never select an existing tenant and grant itself Owner access. New
        # public signups always receive a server-generated isolated tenant.
        tenant = f"org-{uuid.uuid4().hex[:12]}"
        rec = await bootstrap_signup(teams, tenant, email, body.password)
        team_id = rec["team_id"]
        await store.add(User(id=uid, email=rec["email"], password_hash=rec["password_hash"],
                             tenant=tenant, role=Role.owner))
    login_url = f"{settings.public_base_url.rstrip('/')}/login"
    subject, text_body, html_body = welcome_email(login_url=login_url)
    try:
        sent = await run_in_threadpool(
            email_sender.send,
            to=rec["email"],
            subject=subject,
            body=text_body,
            html=html_body,
        )
    except Exception as exc:
        logger.warning("transactional_email_failed", extra={"flow": "welcome", "tenant": tenant})
        raise HTTPException(
            status_code=503,
            detail="account created, but the welcome email could not be sent",
        ) from exc
    if not sent:
        logger.warning("transactional_email_failed", extra={"flow": "welcome", "tenant": tenant})
        raise HTTPException(
            status_code=503,
            detail="account created, but the welcome email could not be sent",
        )
    return {"user_id": uid, "email": rec["email"], "team_id": team_id}


class ForgotBody(BaseModel):
    email: str = Field(min_length=3)


OTP_TTL_SECONDS = 600  # matches OtpStore.issue default (10 minutes)


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotBody,
    otp=Depends(get_otp_store),
    store: UserStore = Depends(get_store),
    email_sender: EmailSender = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> dict:
    email = body.email.strip().lower()
    user = await store.get_by_email(email)
    code: str | None = None
    if user is not None:
        code = await otp.issue(email)
        # Use the configured public app URL so the emailed link points at the deployed app.
        base = settings.public_base_url.rstrip("/")
        reset_url = f"{base}/reset-password?email={quote(email, safe='')}"
        subject, text_body, html_body = password_reset_code_email(
            code, reset_url=reset_url, minutes=OTP_TTL_SECONDS // 60)
        try:
            sent = await run_in_threadpool(
                email_sender.send,
                to=email,
                subject=subject,
                body=text_body,
                html=html_body,
            )
            if not sent:
                logger.warning("transactional_email_failed", extra={"flow": "password_reset"})
        except Exception:
            # Public response stays uniform for existing and unknown addresses. Operations gets a
            # sanitized event without recipient, OTP, provider credentials or raw SMTP details.
            logger.warning("transactional_email_failed", extra={"flow": "password_reset"})
    resp = {"sent": True}
    # Dev convenience only. Gated on the environment, not just the email backend: if ops ever
    # leaves EMAIL_BACKEND=console in preprod/live (e.g. SMTP misconfigured), the OTP must never
    # leak into the HTTP response for a real, non-dev environment.
    if settings.debug and settings.email_backend == "console" and code is not None:
        resp["otp"] = code
    return resp


class ResetBody(BaseModel):
    email: str = Field(min_length=3)
    otp: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8)


@router.post("/reset-password")
async def reset_password(body: ResetBody, otp=Depends(get_otp_store), store: UserStore = Depends(get_store)) -> dict:
    if not await otp.verify(body.email, body.otp):
        raise HTTPException(status_code=400, detail="invalid or expired code")
    user = await store.get_by_email(body.email)
    if user:
        await store.set_password(user.id, hash_password(body.new_password))
    return {"reset": True}
