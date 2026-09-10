"""Client for jm-backend's internal WhatsApp API (JM2-1023 architecture: qiko-core owns the
channel + AI, jm-backend owns business data and is called INTO for it, not the other way round).

Joseph Mews specific (jm-backend is that tenant's own deployable, not a generic multi-tenant
integration), so this lives under joseph_mews/ rather than app/integrations/clients.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    text: str
    template_used: str | None = None
    at: str = ""


@dataclass(frozen=True)
class ConversationState:
    conversation_id: str
    investor_id: int | None
    history: tuple[ConversationTurn, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HandoffPacket:
    """JM2-1031: Joe's structured handoff packet, matching api-spec-whatsapp-joe-agent.md 3.4
    and jm-backend's HandoffPacket schema (app/api/internal_api.py) field-for-field. Sent
    alongside a "joe" turn only when that turn is a handoff - jm-backend maps it onto an
    Enquiry and notifies the assigned agent, it is not stored as conversation history text."""

    reason_code: str
    summary: str
    suggested_next_action: str
    priority: str
    extracted_traits: dict[str, object] = field(default_factory=dict)


class JmBackendClient(Protocol):
    def record_turn(
        self, phone_number: str, role: str, text: str, *,
        template_used: str | None = None, interakt_message_id: str | None = None,
        handoff: HandoffPacket | None = None,
    ) -> ConversationState: ...


class JmBackendError(Exception):
    pass


class HttpJmBackendClient:
    """Implements JmBackendClient via jm-backend's POST /internal/whatsapp/conversations/turn."""

    def __init__(self, base_url: str, shared_secret: str, client: httpx.Client | None = None):
        self._c = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Qiko-Worker-Secret": shared_secret, "Content-Type": "application/json"},
            timeout=10.0,
        )

    def record_turn(
        self, phone_number: str, role: str, text: str, *,
        template_used: str | None = None, interakt_message_id: str | None = None,
        handoff: HandoffPacket | None = None,
    ) -> ConversationState:
        body = {"phone_number": phone_number, "role": role, "text": text}
        if template_used is not None:
            body["template_used"] = template_used
        if interakt_message_id is not None:
            body["interakt_message_id"] = interakt_message_id
        if handoff is not None:
            body["handoff"] = {
                "reason_code": handoff.reason_code,
                "summary": handoff.summary,
                "extracted_traits": handoff.extracted_traits,
                "suggested_next_action": handoff.suggested_next_action,
                "priority": handoff.priority,
            }
        try:
            r = self._c.post("/internal/whatsapp/conversations/turn", json=body)
            r.raise_for_status()
            payload = r.json()
        except httpx.HTTPError as e:
            raise JmBackendError(f"jm-backend call failed: {e}") from e
        return ConversationState(
            conversation_id=payload["conversation_id"],
            investor_id=payload.get("investor_id"),
            history=tuple(
                ConversationTurn(role=m["role"], text=m["text"], template_used=m.get("template_used"),
                                 at=m.get("at", ""))
                for m in payload.get("history", [])
            ),
        )


class UnavailableJmBackendClient:
    """Dev/test default when jm-backend's base URL/secret are not configured. Raises rather than
    silently pretending there is no history, so a caller cannot mistake "not configured" for "new
    lead, empty history"."""

    def record_turn(self, phone_number: str, role: str, text: str, *,
                    template_used: str | None = None, interakt_message_id: str | None = None,
                    handoff: HandoffPacket | None = None) -> ConversationState:
        raise JmBackendError("jm-backend client is not configured (JOE_WORKER_JM_BACKEND_URL/SECRET)")
