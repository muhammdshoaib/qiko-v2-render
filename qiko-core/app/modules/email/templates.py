"""Branded transactional email templates. Returns (subject, body)."""
from __future__ import annotations

BRAND = "Qiko"


def verification_email(link: str) -> tuple[str, str]:
    return (f"Verify your {BRAND} account",
            f"Welcome to {BRAND}. Confirm your email by visiting:\n\n{link}\n\n"
            f"If you did not sign up, ignore this message.")


def password_reset_email(link: str) -> tuple[str, str]:
    return (f"Reset your {BRAND} password",
            f"We received a request to reset your {BRAND} password. Reset it here:\n\n{link}\n\n"
            f"If you did not request this, ignore this message; your password stays the same.")
