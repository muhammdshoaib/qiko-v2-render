"""Public lead-capture forms (enterprise + RAG-wired). Persists the lead and notifies a configured
recipient by email (via the email worker). Minimal validation; no auth (public endpoints)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.email.sender import EmailSender


class LeadError(Exception):
    pass


@dataclass
class Lead:
    kind: str          # enterprise | rag_wired
    name: str
    email: str
    payload: dict = field(default_factory=dict)


@dataclass
class LeadService:
    email: EmailSender
    notify_to: str = "sales@qiko.ai"
    _leads: list[Lead] = field(default_factory=list)

    def capture(self, kind: str, name: str, email: str, payload: dict | None = None) -> Lead:
        if kind not in {"enterprise", "rag_wired"}:
            raise LeadError(f"unknown lead kind: {kind}")
        if not name or "@" not in email:
            raise LeadError("name and a valid email are required")
        lead = Lead(kind=kind, name=name, email=email.lower(), payload=payload or {})
        self._leads.append(lead)
        self.email.send(to=self.notify_to, subject=f"New {kind} lead: {name}",
                        body=f"{name} <{lead.email}>\n\n{lead.payload}")
        return lead

    def all(self) -> list[Lead]:
        return list(self._leads)
