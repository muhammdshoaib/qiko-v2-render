"""Authentication endpoints: login, refresh, logout, me, plus RBAC guards.

Tokens are delivered as httpOnly cookies with a double-submit CSRF token. Single-session
revocation is enforced by matching the token's `sid` against the store's current sid.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
from app.modules.identity import cookies, csrf, tokens, twofa
from app.modules.identity.rbac import Role, role_allows
from app.modules.identity.security import verify_password
from app.modules.identity.store import User, UserStore, seeded_store

router = APIRouter(prefix="/auth", tags=["identity"])

# In-memory by default; swapped for SqlUserStore at startup when USE_DB_STORES is on.
_store: UserStore = seeded_store()


def get_store() -> UserStore:
    return _store


def set_store(store: UserStore) -> None:
    global _store
    _store = store


class LoginRequest(BaseModel):
    email: str
    password: str
    totp: str | None = None


def _public_user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "tenant": u.tenant, "role": u.role.value,
            "twofa_enabled": u.twofa_enabled}


def _require_csrf(request: Request) -> None:
    csrf.require_csrf(request)


@router.post("/login")
async def login(payload: LoginRequest, response: Response, request: Request,
                store: UserStore = Depends(get_store)) -> dict:
    """Authenticate, and record the attempt either way.

    There was no authentication trail of any kind, which is the single most commonly raised finding in
    a SOC 2 CC6.1 sample: the auditor asks for successes AND failures and there is nothing to hand
    over. Failures are the more useful half.

    The failure reason is recorded, and the distinction matters operationally rather than
    theoretically: many failures against many unknown addresses is password spraying, many against one
    known address is a targeted attack, and a wrong 2FA code on a correct password means the password
    itself is already compromised. Collapsing those into "login failed" throws away the only signal
    worth having.

    The response to the caller stays deliberately uniform. "Invalid credentials" for both an unknown
    account and a wrong password is what stops the ENDPOINT being an account-existence oracle; the
    distinction lives only in the audit trail, which is why that trail is gated on view_audit and not
    on view_customers.
    """
    email = payload.email.lower()
    user = await store.get_by_email(email)
    if not user or not verify_password(payload.password, user.password_hash):
        await audit.record(request.app.state.audit, audit.AuditEvent(
            action=audit_actions.LOGIN_FAILED, target_id=email, target_label=email,
            tenant_id=user.tenant if user else None, actor_type=audit.ANONYMOUS,
            outcome=audit.FAILURE,
            metadata={"reason": "bad_password" if user else "unknown_account"}), request=request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    used_backup_code = False
    if user.twofa_enabled:
        provided = payload.totp or ""
        verified = twofa.verify_totp(user.totp_secret or "", provided)
        if not verified:
            verified = await store.consume_backup_code(user.id, provided)
            used_backup_code = verified
        if not verified:
            # The password was correct and only the second factor failed, so this is the event that
            # says a credential is already compromised. It is not the same as a failed password.
            await audit.record(request.app.state.audit, audit.AuditEvent(
                action=audit_actions.MFA_FAILED, target_id=user.id, target_label=email,
                tenant_id=user.tenant, actor_type=audit.USER, actor_id=user.id,
                actor_label=email, outcome=audit.FAILURE,
                metadata={"reason": "missing" if not provided else "invalid"}), request=request)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing 2FA code")
    sid = secrets.token_urlsafe(16)
    if not await store.set_sid_if_password_hash(user.id, user.password_hash, sid):
        await audit.record(request.app.state.audit, audit.AuditEvent(
            action=audit_actions.LOGIN_FAILED, target_id=email, target_label=email,
            tenant_id=user.tenant, actor_type=audit.ANONYMOUS, outcome=audit.FAILURE,
            metadata={"reason": "credentials_changed"}), request=request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    _issue(response, user, sid, mfa=user.twofa_enabled)
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=audit_actions.LOGIN_SUCCEEDED, target_id=user.id, target_label=email,
        tenant_id=user.tenant, actor_type=audit.USER, actor_id=user.id, actor_label=email,
        metadata={"mfa": bool(user.twofa_enabled),
                  # A backup code is single-use and finite, so it is worth surfacing: a customer
                  # signing in with one has lost their authenticator and will need help soon.
                  "backup_code_used": used_backup_code}), request=request)
    return {"user": _public_user(user)}


@router.post("/refresh")
async def refresh(request: Request, response: Response, store: UserStore = Depends(get_store)) -> dict:
    _require_csrf(request)
    raw = request.cookies.get(cookies.REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        claims = tokens.decode_token(raw, expected_type="refresh")
    except tokens.TokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    user = await store.get_by_id(claims["sub"])
    presented_sid = str(claims.get("sid") or "")
    if not user or user.current_sid != presented_sid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")
    sid = secrets.token_urlsafe(16)  # rotate
    if not await store.rotate_sid(user.id, presented_sid, sid):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")
    _issue(response, user, sid, mfa=bool(claims.get("mfa")))
    return {"user": _public_user(user)}


@router.post("/logout")
async def logout(request: Request, response: Response, store: UserStore = Depends(get_store)) -> dict:
    _require_csrf(request)
    raw = request.cookies.get(cookies.ACCESS_COOKIE)
    if raw:
        try:
            claims = tokens.decode_token(raw, expected_type="access")
            await store.set_sid(claims["sub"], None)
        except tokens.TokenError:
            pass
    cookies.clear_auth_cookies(response)
    return {"ok": True}


def _issue(response: Response, user: User, sid: str, *, mfa: bool) -> None:
    access = tokens.create_access_token(user.id, tenant=user.tenant, role=user.role.value,
                                        sid=sid, email=user.email, mfa=mfa)
    refresh_token = tokens.create_refresh_token(user.id, sid=sid, mfa=mfa)
    csrf_token = csrf.generate_csrf_token()
    cookies.set_auth_cookies(response, access, refresh_token, csrf_token)


async def current_user(request: Request, store: UserStore = Depends(get_store)) -> User:
    raw = request.cookies.get(cookies.ACCESS_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        claims = tokens.decode_token(raw, expected_type="access")
    except tokens.TokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    user = await store.get_by_id(claims["sub"])
    if not user or user.current_sid != claims.get("sid"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")
    return user


def require_role(minimum: Role):
    def guard(user: User = Depends(current_user)) -> User:
        if not role_allows(user.role, minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return guard


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"user": _public_user(user)}


class ProfileUpdate(BaseModel):
    name: str | None = None


@router.patch("/me")
async def update_me(body: ProfileUpdate, request: Request,
                    user: User = Depends(current_user), store: UserStore = Depends(get_store)) -> dict:
    """Update the current user's own profile (display name). CSRF-guarded like other state-changing
    auth endpoints; a user may only edit themself (subject comes from the verified access cookie)."""
    _require_csrf(request)
    name = (body.name or "").strip() or None
    if name is not None and len(name) > 255:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "name must be 255 characters or fewer")
    await store.set_name(user.id, name)
    user.name = name
    return {"user": _public_user(user)}
