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
    allowed = {origin.rstrip("/") for origin in settings.cors_allow_origins}
    if source is None:
        if settings.environment is not Environment.dev:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin required")
        return
    if source.rstrip("/") not in allowed and settings.environment is not Environment.dev:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin rejected")
