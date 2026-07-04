"""Short-lived access JWT + rotating refresh JWT (HS256, signed with the session secret).

Single-session revocation is supported via a `sid` (session id) claim: store the current sid
per user and reject tokens whose sid does not match.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

ALGO = "HS256"


class TokenError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(claims: dict, ttl_seconds: int, secret: str) -> str:
    payload = {**claims, "iat": _now(), "exp": _now() + timedelta(seconds=ttl_seconds)}
    return jwt.encode(payload, secret, algorithm=ALGO)


def create_access_token(user_id: str, *, tenant: str | None = None, role: str = "viewer",
                        sid: str | None = None, secret: str | None = None,
                        ttl_seconds: int | None = None) -> str:
    s = get_settings()
    return _encode({"sub": user_id, "type": "access", "tenant": tenant, "role": role, "sid": sid},
                   ttl_seconds or s.access_token_ttl_seconds, secret or s.session_secret)


def create_refresh_token(user_id: str, *, sid: str, secret: str | None = None,
                         ttl_seconds: int | None = None) -> str:
    s = get_settings()
    return _encode({"sub": user_id, "type": "refresh", "sid": sid},
                   ttl_seconds or s.refresh_token_ttl_seconds, secret or s.session_secret)


def decode_token(token: str, *, expected_type: str | None = None, secret: str | None = None) -> dict:
    s = get_settings()
    try:
        claims = jwt.decode(token, secret or s.session_secret, algorithms=[ALGO])
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("invalid token") from e
    if expected_type and claims.get("type") != expected_type:
        raise TokenError(f"expected {expected_type} token")
    return claims
