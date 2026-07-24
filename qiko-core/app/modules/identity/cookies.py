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


def _delete_auth_cookies(response: Response, domain: str | None) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", domain=domain)


def set_auth_cookies(response: Response, access: str, refresh: str, csrf: str) -> None:
    s = get_settings()
    secure = _secure()
    domain = s.cookie_domain or None
    legacy_domain = s.legacy_cookie_domain or None
    if legacy_domain and legacy_domain != domain:
        _delete_auth_cookies(response, legacy_domain)
    response.set_cookie(ACCESS_COOKIE, access, max_age=s.access_token_ttl_seconds,
                        httponly=True, secure=secure, samesite="lax", path="/", domain=domain)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=s.refresh_token_ttl_seconds,
                        httponly=True, secure=secure, samesite="lax", path="/", domain=domain)
    # CSRF cookie is readable by JS (double-submit), so not httpOnly. It must live as long as the
    # REFRESH token, not the (short) access token: /auth/refresh requires a valid CSRF header, so if
    # the CSRF cookie expired with the 15-minute access token the silent refresh would fail and the
    # user would be kicked to login after 15 minutes even with a valid 14-day refresh token.
    response.set_cookie(CSRF_COOKIE, csrf, max_age=s.refresh_token_ttl_seconds,
                        httponly=False, secure=secure, samesite="lax", path="/", domain=domain)


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    domain = settings.cookie_domain or None
    _delete_auth_cookies(response, domain)
    legacy_domain = settings.legacy_cookie_domain or None
    if legacy_domain and legacy_domain != domain:
        _delete_auth_cookies(response, legacy_domain)
