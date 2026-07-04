"""Double-submit CSRF token: the same random token is set as a cookie and sent as a header;
the server checks they match. Protects cookie-based auth from cross-site requests."""
from __future__ import annotations

import hmac
import secrets

CSRF_COOKIE = "qiko_csrf"
CSRF_HEADER = "x-csrf-token"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf(cookie_token: str | None, header_token: str | None) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)
