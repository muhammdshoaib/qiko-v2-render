"""Double-submit CSRF token: the same random token is set as a cookie and sent as a header;
the server checks they match. Protects cookie-based auth from cross-site requests."""
from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from app.core.config import Environment, get_settings

CSRF_COOKIE = "qiko_csrf"
CSRF_HEADER = "x-csrf-token"

# For routes that call require_csrf(request) imperatively (a body model can't carry a header/
# cookie requirement) instead of through a dependency: pass this as the route decorator's
# openapi_extra=, or the generated OpenAPI spec/TS client omit the requirement entirely.
# The header name here is the display form already committed to the OpenAPI spec/TS client by
# the first route that declared it (set_worker_enabled) - CSRF_HEADER is HTTP-header-compared
# case-insensitively, so this differs from it in casing only, not in the actual header matched.
CSRF_OPENAPI_EXTRA = {
    "parameters": [
        {
            "name": "X-CSRF-Token", "in": "header", "required": True,
            "schema": {"type": "string"},
            "description": "Must match the qiko_csrf cookie.",
        },
        {
            "name": CSRF_COOKIE, "in": "cookie", "required": True,
            "schema": {"type": "string"},
            "description": "Double-submit CSRF cookie.",
        },
    ]
}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf(cookie_token: str | None, header_token: str | None) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)


def require_csrf(request: Request) -> None:
    if not validate_csrf(request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF check failed")
    settings = get_settings()
    source = request.headers.get("origin")
    if source is None and (referer := request.headers.get("referer")):
        parts = urlsplit(referer)
        source = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None
    # First-party origins only, never settings.browser_allowed_origins. A partner origin is
    # allowed to read a response in a browser; that is not the same as being trusted to be the
    # Origin of a state-changing request carrying an admin's session cookie, and conflating the
    # two is what QIKO-1102 separated.
    allowed = {origin.rstrip("/") for origin in settings.cors_allow_origins}
    if source is None:
        if settings.environment is not Environment.dev:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin required")
        return
    if source.rstrip("/") not in allowed and settings.environment is not Environment.dev:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin rejected")
