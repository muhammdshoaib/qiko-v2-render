"""httpOnly + Secure + SameSite cookie helpers. Tokens live in cookies, never localStorage."""
from __future__ import annotations

from fastapi import Response

from app.core.config import get_settings
from app.modules.identity.csrf import CSRF_COOKIE

ACCESS_COOKIE = "qiko_access"
REFRESH_COOKIE = "qiko_refresh"


def _secure() -> bool:
    # Secure cookies everywhere except local dev (which may run plain http).
    return not get_settings().debug


def set_auth_cookies(response: Response, access: str, refresh: str, csrf: str) -> None:
    s = get_settings()
    secure = _secure()
    domain = s.cookie_domain or None
    response.set_cookie(ACCESS_COOKIE, access, max_age=s.access_token_ttl_seconds,
                        httponly=True, secure=secure, samesite="lax", path="/", domain=domain)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=s.refresh_token_ttl_seconds,
                        httponly=True, secure=secure, samesite="lax", path="/", domain=domain)
    # CSRF cookie is readable by JS (double-submit), so not httpOnly.
    response.set_cookie(CSRF_COOKIE, csrf, max_age=s.access_token_ttl_seconds,
                        httponly=False, secure=secure, samesite="lax", path="/", domain=domain)


def clear_auth_cookies(response: Response) -> None:
    domain = get_settings().cookie_domain or None
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", domain=domain)
