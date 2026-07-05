"""Authentication endpoints: login, refresh, logout, me, plus RBAC guards.

Tokens are delivered as httpOnly cookies with a double-submit CSRF token. Single-session
revocation is enforced by matching the token's `sid` against the store's current sid.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

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
    return {"id": u.id, "email": u.email, "tenant": u.tenant, "role": u.role.value,
            "twofa_enabled": u.twofa_enabled}


def _require_csrf(request: Request) -> None:
    cookie = request.cookies.get(csrf.CSRF_COOKIE)
    header = request.headers.get(csrf.CSRF_HEADER)
    if not csrf.validate_csrf(cookie, header):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed")


@router.post("/login")
async def login(payload: LoginRequest, response: Response, store: UserStore = Depends(get_store)) -> dict:
    user = await store.get_by_email(payload.email.lower())
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if user.twofa_enabled:
        if not twofa.verify_totp(user.totp_secret or "", payload.totp or ""):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing 2FA code")
    sid = secrets.token_urlsafe(16)
    await store.set_sid(user.id, sid)
    _issue(response, user, sid)
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
    if not user or user.current_sid != claims.get("sid"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")
    sid = secrets.token_urlsafe(16)  # rotate
    await store.set_sid(user.id, sid)
    _issue(response, user, sid)
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


def _issue(response: Response, user: User, sid: str) -> None:
    access = tokens.create_access_token(user.id, tenant=user.tenant, role=user.role.value,
                                        sid=sid, email=user.email)
    refresh_token = tokens.create_refresh_token(user.id, sid=sid)
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
