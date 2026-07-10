"""Public lead-capture forms (enterprise + RAG-wired). Persists the lead and notifies a configured
recipient by email (via the email worker). Minimal validation; no auth (public endpoints)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.modules.email.sender import EmailSender


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LeadError(Exception):
    pass


@dataclass
class Lead:
    id: str
    tenant: str
    kind: str          # enterprise | rag_wired
    name: str
    email: str
    payload: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)


class LeadStore(Protocol):
    async def add(self, lead: Lead) -> Lead: ...
    async def list(self, tenant: str) -> list[Lead]: ...


@dataclass
class InMemoryLeadStore:
    _by_tenant: dict[str, list[Lead]] = field(default_factory=dict)

    async def add(self, lead: Lead) -> Lead:
        self._by_tenant.setdefault(lead.tenant, []).append(lead)
        return lead

    async def list(self, tenant: str) -> list[Lead]:
        return list(self._by_tenant.get(tenant, []))


@dataclass
class LeadService:
    email: EmailSender
    notify_to: str = "sales@qiko.ai"
    store: LeadStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryLeadStore()

    async def capture(self, tenant: str, kind: str, name: str, email: str, payload: dict | None = None) -> Lead:
        if kind not in {"enterprise", "rag_wired"}:
            raise LeadError(f"unknown lead kind: {kind}")
        if not name or "@" not in email:
            raise LeadError("name and a valid email are required")
        lead = Lead(id=uuid.uuid4().hex[:12], tenant=tenant, kind=kind, name=name,
                    email=email.lower(), payload=payload or {})
        await self.store.add(lead)
        self.email.send(to=self.notify_to, subject=f"New {kind} lead: {name}",
                        body=f"{name} <{lead.email}>\n\n{lead.payload}")
        return lead

    async def all(self, tenant: str) -> list[Lead]:
        return await self.store.list(tenant)
