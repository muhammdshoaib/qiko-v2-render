"""Pending email-verification signups for development and persistent SQL stores."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from app.core.config import get_settings
from app.modules.identity.rbac import Role
from app.modules.identity.onboarding import new_otp_code

SIGNUP_VERIFICATION_TTL_SECONDS = 600
SIGNUP_VERIFICATION_MAX_ATTEMPTS = 5

WorkerId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
WorkerName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
WorkerShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
WorkerLongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
WorkerTone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]
WorkerIndustry = Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)]


class _PersistedOnboardingWorkerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    full_name: WorkerName
    title: WorkerShortText
    location: WorkerShortText
    about: WorkerLongText
    tone: WorkerTone
    industry: WorkerIndustry
    expertise: WorkerLongText
    main_goal: WorkerLongText


class PersistedOnboardingWorker(BaseModel):
    """The only accepted JSON shape for a pending signup's worker draft."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: WorkerId
    name: WorkerName
    config: _PersistedOnboardingWorkerConfig
    knowledge: WorkerLongText


def parse_persisted_onboarding_worker(value: object | None) -> dict | None:
    if value is None:
        return None
    return PersistedOnboardingWorker.model_validate(value, strict=True).model_dump()


def hash_signup_code(code: str) -> str:
    message = f"signup-verification:{code}".encode()
    return hmac.new(get_settings().session_secret.encode(), message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class PendingSignup:
    user_id: str
    email: str
    password_hash: str
    tenant: str
    role: Role
    code_hash: str
    expires_at: datetime
    terms_release_id: str
    privacy_release_id: str
    cookies_release_id: str
    # The display name typed at signup. It used to be collected by the form and silently dropped,
    # so every account was created with no name even though users.name exists.
    name: str | None = None
    onboarding_worker: dict | None = None
    invite_version: int | None = None
    attempts_remaining: int = SIGNUP_VERIFICATION_MAX_ATTEMPTS
    completed_at: datetime | None = None
    completed_team_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PendingSignupStore(Protocol):
    async def put(self, signup: PendingSignup) -> bool: ...
    async def get(self, email: str) -> PendingSignup | None: ...
    async def consume(self, email: str, code: str) -> PendingSignup | None: ...
    async def delete(self, email: str) -> None: ...
    async def purge_expired(self) -> int: ...
    async def finalize_signup(self, email: str, code: str, password_hash: str, terms_release_id: str, privacy_release_id: str, cookies_release_id: str) -> tuple[PendingSignup, bool] | None: ...


@dataclass
class InMemoryPendingSignupStore:
    """Single-process pending signup store with hashed, expiring, one-time codes."""

    _pending: dict[str, PendingSignup] = field(default_factory=dict)
    _monotonic_expiry: dict[str, float] = field(default_factory=dict)
    _claimed: set[str] = field(default_factory=set)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def put(self, signup: PendingSignup) -> bool:
        signup = replace(
            signup,
            onboarding_worker=parse_persisted_onboarding_worker(signup.onboarding_worker),
        )
        email = signup.email.lower()
        async with self._lock:
            existing = await self.get(email)
            if existing is not None:
                return False
            self._pending[email] = signup
            remaining = max(0.0, (signup.expires_at - datetime.now(timezone.utc)).total_seconds())
            self._monotonic_expiry[email] = time.monotonic() + remaining
            return True

    async def get(self, email: str) -> PendingSignup | None:
        key = email.lower()
        signup = self._pending.get(key)
        if signup is not None and self._monotonic_expiry.get(key, 0) <= time.monotonic():
            self._pending.pop(key, None)
            self._monotonic_expiry.pop(key, None)
            return None
        return signup

    async def consume(self, email: str, code: str) -> PendingSignup | None:
        key = email.lower()
        async with self._lock:
            signup = await self.get(key)
            if signup is None or key in self._claimed:
                return None
            try:
                signup = replace(
                    signup,
                    onboarding_worker=parse_persisted_onboarding_worker(signup.onboarding_worker),
                )
            except ValidationError:
                return None
            if not secrets.compare_digest(signup.code_hash, hash_signup_code(code)):
                remaining = signup.attempts_remaining - 1
                if remaining <= 0:
                    self._pending.pop(key, None)
                    self._monotonic_expiry.pop(key, None)
                else:
                    self._pending[key] = replace(signup, attempts_remaining=remaining)
                return None
            self._claimed.add(key)
            return signup

    async def release(self, email: str) -> None:
        async with self._lock:
            self._claimed.discard(email.lower())

    async def delete(self, email: str) -> None:
        key = email.lower()
        self._pending.pop(key, None)
        self._monotonic_expiry.pop(key, None)
        self._claimed.discard(key)

    async def purge_expired(self) -> int:
        expired = [key for key, expiry in self._monotonic_expiry.items() if expiry <= time.monotonic()]
        for key in expired:
            self._pending.pop(key, None)
            self._monotonic_expiry.pop(key, None)
        return len(expired)


def make_pending_signup(
    *,
    user_id: str,
    email: str,
    password_hash: str,
    tenant: str,
    role: Role,
    terms_release_id: str,
    privacy_release_id: str,
    cookies_release_id: str,
    name: str | None = None,
    onboarding_worker: dict | None = None,
    invite_version: int | None = None,
    ttl: int = SIGNUP_VERIFICATION_TTL_SECONDS,
) -> tuple[PendingSignup, str]:
    if invite_version is not None and onboarding_worker is not None:
        raise ValueError("invited signup cannot create an onboarding worker")
    onboarding_worker = parse_persisted_onboarding_worker(onboarding_worker)
    code = new_otp_code()
    return PendingSignup(
        user_id=user_id,
        email=email.lower(),
        password_hash=password_hash,
        tenant=tenant,
        role=role,
        code_hash=hash_signup_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
        terms_release_id=terms_release_id,
        privacy_release_id=privacy_release_id,
        cookies_release_id=cookies_release_id,
        name=name,
        onboarding_worker=onboarding_worker,
        invite_version=invite_version,
    ), code
