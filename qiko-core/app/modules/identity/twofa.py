"""TOTP two-factor authentication (RFC 6238) via pyotp."""
from __future__ import annotations

import secrets
import string

import pyotp


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str, issuer: str = "Qiko") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=valid_window)


def normalize_backup_code(code: str) -> str:
    return code.strip().replace("-", "").replace(" ", "").upper()


def backup_code_selector(code: str) -> str | None:
    normalized = normalize_backup_code(code)
    if len(normalized) != 24 or any(char not in string.hexdigits for char in normalized):
        return None
    return normalized[:4]


def new_backup_codes(count: int = 10) -> list[str]:
    codes: dict[str, str] = {}
    while len(codes) < count:
        raw = secrets.token_hex(12).upper()
        codes.setdefault(raw[:4], "-".join(raw[index:index + 4] for index in range(0, 24, 4)))
    return list(codes.values())
