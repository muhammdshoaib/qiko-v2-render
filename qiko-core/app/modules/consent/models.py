"""Legal policy release and append-only consent domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

TERMS_RELEASE_ID = "terms-2026-07-24"
PRIVACY_RELEASE_ID = "privacy-2026-07-24"
COOKIES_RELEASE_ID = "cookies-2026-07-24"

CURRENT_POLICY_RELEASES = {
    TERMS_RELEASE_ID: ("terms", "0005d9a75e20191854111bdfc210abe8f6bc965e2925103efdff2541fe37b813"),
    PRIVACY_RELEASE_ID: ("privacy", "2a80152571cbc4b855edd995ee9de978ba967adeeedd2f6f3352f8fd5a30aadc"),
    COOKIES_RELEASE_ID: ("cookies", "2db07436eef3b54526a20e65358c7d3f62fedeceddca332ecd7bb371688abb0c"),
}

ConsentSource = Literal["anonymous", "authenticated", "signup"]
ConsentAction = Literal["accept", "reject", "update", "withdraw"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PolicyRelease:
    id: str
    policy_type: str
    content_sha256: str
    effective_at: datetime


@dataclass(frozen=True)
class ConsentChoices:
    preferences: bool
    analytics: bool
    marketing: bool


@dataclass(frozen=True)
class ConsentRecord:
    id: str
    decision_id: str
    revision: int
    client_revision: int
    key_version: str
    subject_hmac: str
    preferences: bool
    analytics: bool
    marketing: bool
    source: ConsentSource
    action: ConsentAction
    terms_release_id: str = TERMS_RELEASE_ID
    privacy_release_id: str = PRIVACY_RELEASE_ID
    cookies_release_id: str = COOKIES_RELEASE_ID
    created_at: datetime = field(default_factory=utcnow)
