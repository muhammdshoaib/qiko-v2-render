"""Symmetric encryption for secrets at rest (per-user channel tokens, etc.).

Fernet (AES-128-CBC + HMAC) keyed from the app secret. Replaces the legacy plaintext token
storage in the channel session stores. In prod the key comes from a dedicated secret, not the
session secret; keep the same interface.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().session_secret.encode()).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
