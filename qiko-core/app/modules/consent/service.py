"""Consent recording with pseudonymous subjects and server-derived audit metadata."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import get_settings
from app.modules.consent.models import (
    CURRENT_POLICY_RELEASES,
    TERMS_RELEASE_ID,
    PRIVACY_RELEASE_ID,
    COOKIES_RELEASE_ID,
    ConsentAction,
    ConsentChoices,
    ConsentRecord,
    ConsentSource,
    PolicyRelease,
    utcnow,
)


class ConsentStore(Protocol):
    async def add(self, record: ConsentRecord) -> ConsentRecord: ...
    async def get(self, decision_id: str) -> ConsentRecord | None: ...
    async def latest(self, subject_hmac: str) -> ConsentRecord | None: ...
    async def list_policy_releases(self) -> list[PolicyRelease]: ...


@dataclass
class InMemoryConsentStore:
    """Development store. It intentionally exposes no update/delete operations."""

    _records: tuple[ConsentRecord, ...] = field(default_factory=tuple)
    policy_releases: dict[str, PolicyRelease] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.policy_releases:
            effective_at = utcnow().replace(year=2026, month=7, day=24, hour=0, minute=0, second=0, microsecond=0)
            self.policy_releases = {
                release_id: PolicyRelease(release_id, policy_type, digest, effective_at)
                for release_id, (policy_type, digest) in CURRENT_POLICY_RELEASES.items()
            }

    @property
    def records(self) -> tuple[ConsentRecord, ...]:
        return self._records

    async def add(self, record: ConsentRecord) -> ConsentRecord:
        existing = await self.get(record.decision_id)
        if existing is not None:
            return existing
        self._records = (*self._records, record)
        return record

    async def get(self, decision_id: str) -> ConsentRecord | None:
        return next((record for record in self._records if record.decision_id == decision_id), None)

    async def latest(self, subject_hmac: str) -> ConsentRecord | None:
        return next((record for record in reversed(self._records) if record.subject_hmac == subject_hmac), None)

    async def list_policy_releases(self) -> list[PolicyRelease]:
        return list(self.policy_releases.values())


def _pseudonym_keyring() -> tuple[str, dict[str, str]]:
    settings = get_settings()
    keys = getattr(settings, "consent_pseudonym_keys", {})
    active = getattr(settings, "consent_pseudonym_active_version", "v1")
    if not keys:
        keys = {"v1": settings.encryption_key or settings.session_secret}
    return active, keys


def active_pseudonym_version() -> str:
    return _pseudonym_keyring()[0]


def pseudonymous_subject(namespace: str, identifier: str, key_version: str | None = None) -> str:
    """Return a one-way, keyed identifier. The raw user or browser identifier is never stored."""

    active, keys = _pseudonym_keyring()
    version = key_version or active
    root = keys[version].encode()
    key = hmac.new(root, f"consent-pseudonym:{version}".encode(), hashlib.sha256).digest()
    message = f"legal-consent:{namespace}:{identifier}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def same_consent_decision(existing: ConsentRecord, candidate: ConsentRecord) -> bool:
    return (
        existing.decision_id == candidate.decision_id
        and existing.subject_hmac == candidate.subject_hmac
        and existing.revision == candidate.revision
        and existing.client_revision == candidate.client_revision
        and existing.key_version == candidate.key_version
        and existing.preferences == candidate.preferences
        and existing.analytics == candidate.analytics
        and existing.marketing == candidate.marketing
        and existing.source == candidate.source
        and existing.terms_release_id == candidate.terms_release_id
        and existing.privacy_release_id == candidate.privacy_release_id
        and existing.cookies_release_id == candidate.cookies_release_id
    )


def derive_action(previous: ConsentRecord | None, choices: ConsentChoices) -> ConsentAction:
    optional = (choices.preferences, choices.analytics, choices.marketing)
    if previous is None:
        return "accept" if any(optional) else "reject"
    previous_optional = (previous.preferences, previous.analytics, previous.marketing)
    if not any(optional) and any(previous_optional):
        return "withdraw"
    return "update"


@dataclass
class ConsentService:
    store: ConsentStore = field(default_factory=InMemoryConsentStore)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def record(
        self,
        *,
        namespace: str,
        identifier: str,
        choices: ConsentChoices,
        source: ConsentSource,
        decision_id: str | None = None,
        revision: int | None = None,
        client_revision: int | None = None,
        terms_release_id: str = TERMS_RELEASE_ID,
        privacy_release_id: str = PRIVACY_RELEASE_ID,
        cookies_release_id: str = COOKIES_RELEASE_ID,
    ) -> ConsentRecord:
        key_version, keys = _pseudonym_keyring()
        subject_hmac = pseudonymous_subject(namespace, identifier, key_version)
        subject_hmacs = [pseudonymous_subject(namespace, identifier, version) for version in keys]
        decision_id = decision_id or uuid.uuid4().hex
        assigned_client_revision = client_revision if client_revision is not None else int(utcnow().timestamp() * 1000)
        if assigned_client_revision > int(utcnow().timestamp() * 1000) + 300_000:
            raise ValueError("consent decision revision is too far in the future")
        record_decision = getattr(self.store, "record_decision", None)
        if record_decision is not None and revision is None:
            return await record_decision(
                subject_hmac=subject_hmac, subject_hmacs=subject_hmacs,
                key_version=key_version, decision_id=decision_id,
                client_revision=assigned_client_revision, choices=choices, source=source,
                terms_release_id=terms_release_id, privacy_release_id=privacy_release_id,
                cookies_release_id=cookies_release_id)
        async with self._lock:
            existing = await self.store.get(decision_id)
            if existing is not None:
                candidate = ConsentRecord(
                    id=existing.id, decision_id=decision_id,
                    revision=revision if revision is not None else existing.revision,
                    client_revision=assigned_client_revision,
                    key_version=existing.key_version,
                    subject_hmac=existing.subject_hmac if existing.subject_hmac in subject_hmacs else subject_hmac,
                    preferences=choices.preferences, analytics=choices.analytics,
                    marketing=choices.marketing, source=source, action=existing.action,
                    terms_release_id=terms_release_id, privacy_release_id=privacy_release_id,
                    cookies_release_id=cookies_release_id, created_at=existing.created_at)
                if not same_consent_decision(existing, candidate):
                    raise ValueError("consent decision id conflict")
                return existing
            previous = await self.latest(namespace=namespace, identifier=identifier)
            if client_revision is None and previous is not None:
                assigned_client_revision = max(assigned_client_revision, previous.client_revision + 1)
            if previous is not None and assigned_client_revision < previous.client_revision:
                raise ValueError("stale consent decision")
            if previous is not None and assigned_client_revision == previous.client_revision:
                merged = ConsentChoices(
                    previous.preferences and choices.preferences,
                    previous.analytics and choices.analytics,
                    previous.marketing and choices.marketing)
                if (merged.preferences, merged.analytics, merged.marketing) == (
                        previous.preferences, previous.analytics, previous.marketing):
                    raise ValueError("stale consent decision")
                choices = merged
            assigned_revision = revision if revision is not None else (
                previous.revision + 1 if previous else 1)
            if previous is not None and assigned_revision <= previous.revision:
                raise ValueError("stale consent revision")
            action: ConsentAction = "accept" if source == "signup" else derive_action(previous, choices)
            record = ConsentRecord(
                id=uuid.uuid4().hex, decision_id=decision_id, revision=assigned_revision,
                client_revision=assigned_client_revision,
                key_version=key_version, subject_hmac=subject_hmac,
                preferences=choices.preferences, analytics=choices.analytics,
                marketing=choices.marketing, source=source, action=action,
                terms_release_id=terms_release_id, privacy_release_id=privacy_release_id,
                cookies_release_id=cookies_release_id, created_at=utcnow())
            return await self.store.add(record)

    async def latest(self, *, namespace: str, identifier: str) -> ConsentRecord | None:
        _, keys = _pseudonym_keyring()
        records = [await self.store.latest(pseudonymous_subject(namespace, identifier, version))
                   for version in keys]
        found = [record for record in records if record is not None]
        return max(found, key=lambda record: record.revision) if found else None
