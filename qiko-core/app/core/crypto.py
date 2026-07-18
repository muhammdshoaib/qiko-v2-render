"""Symmetric encryption for secrets at rest (per-user channel tokens, etc.).

Fernet (AES-128-CBC + HMAC) keyed from a DEDICATED encryption secret (ENCRYPTION_KEY), not the
session secret: the two rotate independently, so rotating SESSION_SECRET never bricks the
encrypted-at-rest secrets (Vapi keys, Salesforce secrets/tokens, channel tokens).

When ENCRYPTION_KEY is set, new writes use the key derived from it, but decryption still falls
back (via MultiFernet) to the legacy session_secret-derived key so ciphertext written before the
dedicated key existed keeps decrypting. When ENCRYPTION_KEY is unset (e.g. dev) we keep the
legacy session_secret derivation, so nothing changes without the new env var.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, MultiFernet

from app.core.config import get_settings


def _derive_key(secret: str) -> bytes:
    """A URL-safe base64 32-byte Fernet key derived from an arbitrary-length secret string."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def _fernet() -> MultiFernet:
    """MultiFernet whose FIRST key is used for encryption and ALL keys are tried for decryption.

    With a dedicated encryption_key set: [dedicated, legacy] -> new writes use the dedicated key,
    old ciphertext (encrypted under the session_secret-derived key) still decrypts via the fallback.
    Without it: [legacy] -> unchanged behaviour.
    """
    settings = get_settings()
    legacy = _derive_key(settings.session_secret)
    if settings.encryption_key:
        keys = [_derive_key(settings.encryption_key), legacy]
    else:
        keys = [legacy]
    return MultiFernet([Fernet(k) for k in keys])


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
