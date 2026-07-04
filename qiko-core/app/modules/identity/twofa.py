"""TOTP two-factor authentication (RFC 6238) via pyotp."""
from __future__ import annotations

import pyotp


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str, issuer: str = "Qiko") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=valid_window)
