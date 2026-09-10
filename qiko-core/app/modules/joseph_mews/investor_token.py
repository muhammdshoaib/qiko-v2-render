"""Investor activity token (JM2-1131).

A short-lived, signed token that lets an investor-facing backend (jm-backend,
joseph-mews-backend, or any future equivalent) authorize its own investor's mobile app to sync
activity directly to qiko-core, without a live call back to that backend per event and without
the investor ever needing a Qiko user account of their own. Deliberately generic: either backend
can mint one as long as it holds the shared secret, since qiko-core does not care which system
authenticated the investor originally.

Uses its own secret (investor_activity_token_secret, app/core/config.py) and its own `type`
claim, distinct from session_secret/identity.tokens' access tokens and from
jm_backend_shared_secret/jm_backend_api_key -- confusing this with another credential class would
let one kind of token impersonate another.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

_ALGO = "HS256"
_TOKEN_TYPE = "investor_activity"


class InvestorTokenError(Exception):
    pass


def create_investor_activity_token(
    *, tenant: str, investor_ref: str, secret: str | None = None, ttl_seconds: int | None = None,
) -> str:
    """investor_ref is opaque: whatever stable per-investor identifier the issuing backend uses
    internally. Never a property/development/document id (those must never appear in activity
    data at all), but the investor's own identity is required, since activity is explicitly
    "keyed by user"."""
    s = get_settings()
    resolved_secret = secret if secret is not None else s.investor_activity_token_secret
    if not resolved_secret:
        raise InvestorTokenError("investor_activity_token_secret is not configured")
    now = datetime.now(UTC)
    ttl = ttl_seconds if ttl_seconds is not None else s.investor_activity_token_ttl_seconds
    payload = {
        "type": _TOKEN_TYPE, "tenant": tenant, "investor_ref": investor_ref,
        "iat": now, "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, resolved_secret, algorithm=_ALGO)


def decode_investor_activity_token(token: str, *, secret: str | None = None) -> dict:
    s = get_settings()
    resolved_secret = secret if secret is not None else s.investor_activity_token_secret
    if not resolved_secret:
        raise InvestorTokenError("investor_activity_token_secret is not configured")
    try:
        claims = jwt.decode(token, resolved_secret, algorithms=[_ALGO])
    except jwt.ExpiredSignatureError as e:
        raise InvestorTokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise InvestorTokenError("invalid token") from e
    if claims.get("type") != _TOKEN_TYPE:
        raise InvestorTokenError(f"expected a {_TOKEN_TYPE} token")
    if not claims.get("tenant") or not claims.get("investor_ref"):
        raise InvestorTokenError("token missing tenant/investor_ref")
    return claims
