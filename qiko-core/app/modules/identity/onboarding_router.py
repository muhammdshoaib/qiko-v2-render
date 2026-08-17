"""Signup bootstrap + OTP password reset (public identity flows)."""
from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import replace
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.deps import get_agents, get_knowledge, get_otp_store, get_pending_invites, get_teams
from app.modules.agents.service import Agent, build_worker_created_audit_row
from app.modules.email.sender import EmailSender, get_email_sender
from app.modules.email.templates import password_reset_code_email, welcome_email
from app.modules.consent.models import (
    COOKIES_RELEASE_ID,
    PRIVACY_RELEASE_ID,
    TERMS_RELEASE_ID,
    ConsentChoices,
)
from app.modules.consent.service import ConsentService
from app.modules.identity.pending_signup import (
    SIGNUP_VERIFICATION_TTL_SECONDS,
    PendingSignup,
    PendingSignupStore,
    WorkerIndustry,
    WorkerLongText,
    WorkerName,
    WorkerShortText,
    WorkerTone,
    make_pending_signup,
    parse_persisted_onboarding_worker,
)
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.identity.security import hash_password
from app.modules.identity.store import User, UserStore
from app.modules.identity.team_access import ASSIGNABLE_ROLES, PendingInviteStore
from app.modules.identity.tokens import TokenError, decode_token
from app.modules.identity import cookies, csrf, tokens

router = APIRouter(prefix="/auth", tags=["identity"])
logger = logging.getLogger(__name__)


class OnboardingWorkerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WorkerName
    title: WorkerShortText
    location: WorkerShortText
    about: WorkerLongText
    tone: WorkerTone
    industry: WorkerIndustry
    expertise: WorkerLongText
    main_goal: WorkerLongText
    knowledge: WorkerLongText


class SignupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # `tenant` remains accepted for backwards-compatible clients but is never trusted. Public signup
    # receives a server-generated tenant; invited signup derives membership from a signed token.
    tenant: str | None = None
    email: str = Field(min_length=3)
    # Password is selected once during email verification, not collected (and ignored) at signup.
    password: str | None = Field(default=None, min_length=8)
    # The signup form always collected a name; it was dropped on the way in, so every account was
    # created nameless even though users.name exists and Settings renders a display name.
    name: str | None = Field(default=None, max_length=255)
    invite_token: str | None = None
    onboarding_worker: OnboardingWorkerBody | None = None
    accept_policies: Literal[True]
    terms_release_id: Literal["terms-2026-07-24"]
    privacy_release_id: Literal["privacy-2026-07-24"]
    cookies_release_id: Literal["cookies-2026-07-24"]


def _canonical_onboarding_worker(worker: OnboardingWorkerBody) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "name": worker.name,
        "config": {
            "full_name": worker.name,
            "title": worker.title,
            "location": worker.location,
            "about": worker.about,
            "tone": worker.tone,
            "industry": worker.industry,
            "expertise": worker.expertise,
            "main_goal": worker.main_goal,
        },
        "knowledge": worker.knowledge,
    }


def get_pending_signups(request: Request) -> PendingSignupStore:
    return request.app.state.pending_signups


def get_signup_consent(request: Request) -> ConsentService:
    return request.app.state.consent


@router.post("/signup", status_code=202)
async def signup(
    body: SignupBody,
    store: UserStore = Depends(get_store),
    pending_invites: PendingInviteStore = Depends(get_pending_invites),
    pending_signups: PendingSignupStore = Depends(get_pending_signups),
    email_sender: EmailSender = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> dict:
    email = body.email.strip().lower()
    if body.invite_token is not None and body.onboarding_worker is not None:
        raise HTTPException(status_code=400, detail="invited signup cannot create an onboarding worker")
    if await store.get_by_email(email) is not None:
        raise HTTPException(status_code=409, detail="an account with that email already exists")

    role = Role.owner
    invite_version: int | None = None
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
        invite = await pending_invites.get(tenant, email)
        if (invite is None or invite.role != role
                or int(invite.invited_at * 1_000_000) != invite_version):
            raise HTTPException(status_code=400, detail="invitation is no longer pending")
    else:
        # Public callers cannot choose an existing tenant or grant themselves access to it.
        tenant = f"org-{uuid.uuid4().hex[:12]}"

    candidate, code = make_pending_signup(
        user_id=uuid.uuid4().hex[:12],
        email=email,
        password_hash="",
        tenant=tenant,
        role=role,
        terms_release_id=body.terms_release_id,
        privacy_release_id=body.privacy_release_id,
        cookies_release_id=body.cookies_release_id,
        name=(body.name or "").strip() or None,
        onboarding_worker=(
            _canonical_onboarding_worker(body.onboarding_worker)
            if body.onboarding_worker is not None
            else None
        ),
        invite_version=invite_version,
    )
    created = await pending_signups.put(candidate)
    if not created:
        return {"verification_required": True, "email": email,
                "expires_in": SIGNUP_VERIFICATION_TTL_SECONDS}

    verify_url = f"{settings.public_base_url.rstrip('/')}/verify-email?email={quote(email, safe='')}"
    text_body = (
        f"Your Qiko verification code is {code}.\n\n"
        f"Enter this one-time code at {verify_url}. It expires in 10 minutes."
    )
    html_body = (
        "<p>Your Qiko verification code is:</p>"
        f"<p><strong>{code}</strong></p>"
        f'<p>Enter it at <a href="{verify_url}">Verify email</a>. It expires in 10 minutes.</p>'
    )
    try:
        sent = await run_in_threadpool(
            email_sender.send,
            to=email,
            subject="Verify your Qiko email",
            body=text_body,
            html=html_body,
        )
    except Exception as exc:
        await pending_signups.delete(email)
        logger.warning("transactional_email_failed", extra={"flow": "signup_verification"})
        raise HTTPException(status_code=503, detail="verification email could not be sent") from exc
    if not sent:
        await pending_signups.delete(email)
        logger.warning("transactional_email_failed", extra={"flow": "signup_verification"})
        raise HTTPException(status_code=503, detail="verification email could not be sent")

    response = {
        "verification_required": True,
        "email": email,
        "expires_in": SIGNUP_VERIFICATION_TTL_SECONDS,
    }
    if settings.debug and settings.email_backend == "console":
        response["verification_code"] = code
    return response


class VerifySignupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3)
    code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=8, max_length=256)
    accept_policies: Literal[True]
    terms_release_id: Literal[TERMS_RELEASE_ID]
    privacy_release_id: Literal[PRIVACY_RELEASE_ID]
    cookies_release_id: Literal[COOKIES_RELEASE_ID]


class VerifySignupResponse(BaseModel):
    user_id: str
    email: str
    team_id: str | None
    worker_id: str | None = None


def _verification_response(
    candidate: PendingSignup,
    email: str,
    team_id: str | None,
) -> VerifySignupResponse:
    worker_id = (
        candidate.onboarding_worker["id"]
        if candidate.onboarding_worker is not None
        else None
    )
    return VerifySignupResponse(
        user_id=candidate.user_id,
        email=email,
        team_id=team_id,
        worker_id=worker_id,
    )


async def _create_onboarding_worker(candidate: PendingSignup, agents, knowledge) -> None:
    worker = parse_persisted_onboarding_worker(candidate.onboarding_worker)
    if worker is None:
        return
    agent = Agent(
        id=worker["id"],
        tenant=candidate.tenant,
        name=worker["name"],
        atype="worker",
        status="training",
        config=dict(worker["config"]),
        enabled=True,
    )
    await agents.store.add(agent, audit=build_worker_created_audit_row(
        tenant=candidate.tenant,
        worker_id=agent.id,
        worker_type=agent.atype,
        status=agent.status,
        source="onboarding",
    ))
    await knowledge.ingest(
        candidate.tenant,
        worker["id"],
        worker["knowledge"],
        agent_id=worker["id"],
    )


def _user_from_candidate(candidate: PendingSignup, password: str) -> User:
    return User(
        id=candidate.user_id,
        email=candidate.email,
        password_hash=hash_password(password),
        tenant=candidate.tenant,
        role=candidate.role,
        name=candidate.name,
        twofa_enabled=False,
    )


async def _issue_session(response: Response, user: User, store: UserStore) -> None:
    """Issue an authenticated session for a freshly-verified user."""
    sid = secrets.token_urlsafe(16)
    await store.set_sid(user.id, sid)
    access = tokens.create_access_token(
        user.id, tenant=user.tenant, role=user.role.value, sid=sid, email=user.email, mfa=user.twofa_enabled
    )
    refresh = tokens.create_refresh_token(user.id, sid=sid, mfa=user.twofa_enabled)
    csrf_token = csrf.generate_csrf_token()
    cookies.set_auth_cookies(response, access, refresh, csrf_token)


@router.post(
    "/verify-email",
    response_model=VerifySignupResponse,
    response_model_exclude_none=True,
)
async def verify_signup(
    body: VerifySignupBody,
    response: Response,
    store: UserStore = Depends(get_store),
    agents=Depends(get_agents),
    knowledge=Depends(get_knowledge),
    teams=Depends(get_teams),
    pending_invites: PendingInviteStore = Depends(get_pending_invites),
    pending_signups: PendingSignupStore = Depends(get_pending_signups),
    consent: ConsentService = Depends(get_signup_consent),
    email_sender: EmailSender = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> VerifySignupResponse:
    email = body.email.strip().lower()
    finalize_signup = getattr(pending_signups, "finalize_signup", None)
    if finalize_signup is not None:
        finalized = await finalize_signup(
            email, body.code, hash_password(body.password), body.terms_release_id,
            body.privacy_release_id, body.cookies_release_id)
        if finalized is None:
            raise HTTPException(status_code=400, detail="invalid or expired verification code")
        candidate, created = finalized
        if created:
            login_url = f"{settings.public_base_url.rstrip('/')}/login"
            subject, text_body, html_body = welcome_email(login_url=login_url)
            try:
                await run_in_threadpool(email_sender.send, to=email, subject=subject, body=text_body, html=html_body)
            except Exception:
                logger.warning("transactional_email_failed", extra={"flow": "signup_welcome"})
            await _issue_session(response, _user_from_candidate(candidate, body.password), store)
        return _verification_response(candidate, email, candidate.completed_team_id)

    candidate = await pending_signups.consume(email, body.code)
    if candidate is None:
        raise HTTPException(status_code=400, detail="invalid or expired verification code")
    try:
        candidate = replace(
            candidate,
            onboarding_worker=parse_persisted_onboarding_worker(candidate.onboarding_worker),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="invalid or expired verification code") from exc
    if await store.get_by_email(email) is not None:
        raise HTTPException(status_code=409, detail="an account with that email already exists")

    if candidate.invite_version is not None:
        invite = await pending_invites.get(candidate.tenant, email)
        if (invite is None or invite.role != candidate.role
                or int(invite.invited_at * 1_000_000) != candidate.invite_version):
            raise HTTPException(status_code=400, detail="invitation is no longer pending")

    # Legal evidence must commit before a login-capable User is created.
    await consent.record(
        namespace="user",
        identifier=candidate.user_id,
        choices=ConsentChoices(preferences=False, analytics=False, marketing=False),
        source="signup",
        decision_id=f"signup:{candidate.user_id}",
        terms_release_id=body.terms_release_id,
        privacy_release_id=body.privacy_release_id,
        cookies_release_id=body.cookies_release_id,
    )

    team_id: str | None = None
    if candidate.invite_version is None:
        team = await teams.create_team(candidate.tenant, email)
        team_id = team.id
    user = User(
        id=candidate.user_id,
        email=email,
        password_hash=hash_password(body.password),
        tenant=candidate.tenant,
        role=candidate.role,
        name=candidate.name,
    )
    await store.add(user)
    await _create_onboarding_worker(candidate, agents, knowledge)
    if candidate.invite_version is not None:
        await pending_invites.remove(candidate.tenant, email)
    await pending_signups.delete(email)

    login_url = f"{settings.public_base_url.rstrip('/')}/login"
    subject, text_body, html_body = welcome_email(login_url=login_url)
    try:
        sent = await run_in_threadpool(
            email_sender.send,
            to=email,
            subject=subject,
            body=text_body,
            html=html_body,
        )
        if not sent:
            logger.warning("transactional_email_failed", extra={"flow": "welcome", "tenant": candidate.tenant})
    except Exception:
        # Verification already succeeded and its code is consumed. Do not report a retryable failure
        # after creating the account, because a retry cannot reuse the one-time code.
        logger.warning("transactional_email_failed", extra={"flow": "welcome", "tenant": candidate.tenant})
    await _issue_session(response, user, store)
    return _verification_response(candidate, email, team_id)


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
async def reset_password(body: ResetBody, request: Request, otp=Depends(get_otp_store),
                         store: UserStore = Depends(get_store)) -> dict:
    """Set a new password from a one-time code.

    An unauthenticated endpoint that changes who can log in, which makes it the most consequential
    thing in this module and the one that recorded nothing. Note the deliberate silence in the
    response: a valid code for an address with no account still returns {"reset": true}, so the
    endpoint is not an account-existence oracle. The audit records what actually happened.

    No fingerprint of the password, unlike the integration credentials. A keyed truncated HMAC of a
    human-chosen password, across many users, is a correlation risk that buys nothing: nobody needs to
    know whether a password was reused, only that it changed and by which route.
    """
    if not await otp.verify(body.email, body.otp):
        await audit.record(request.app.state.audit, audit.AuditEvent(
            action=audit_actions.PASSWORD_RESET_REQUESTED, target_id=body.email,
            target_label=body.email, actor_type=audit.ANONYMOUS, outcome=audit.FAILURE,
            metadata={"reason": "invalid_or_expired_code"}), request=request)
        raise HTTPException(status_code=400, detail="invalid or expired code")
    user = await store.get_by_email(body.email)
    password_changed = bool(user and await store.set_password_and_revoke_sessions(
        user.id, hash_password(body.new_password)))
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.PASSWORD_CHANGED, target_id=user.id if user else body.email,
        target_label=body.email, tenant_id=user.tenant if user else None,
        actor_type=audit.ANONYMOUS, outcome=audit.SUCCESS if password_changed else audit.FAILURE,
        changes=audit.diff(audit_actions.PASSWORD_CHANGED, {}, {"method": "reset_token"}),
        # Recorded because the endpoint deliberately does not tell the caller: a reset against an
        # address with no account is either a typo or reconnaissance, and only this row distinguishes
        # them later.
        metadata={"account_existed": bool(user)}), request=request)
    return {"reset": True}
