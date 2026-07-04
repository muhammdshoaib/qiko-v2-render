"""WhatsApp (Meta Graph) adapter: strict webhook verification, inbound dedup + extraction, and
outbound sending behind a gateway. Inbound text is routed to the worker via agentcore; voice notes
are transcribed by the Bedrock Nova Sonic worker (SCRUM-33)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.channels.webhooks import IdempotencyGuard


def verify_webhook(mode: str, token: str, challenge: str, *, expected_token: str) -> str | None:
    """Meta subscription handshake. Strict: only echoes the challenge on an exact token match."""
    if mode == "subscribe" and expected_token and token == expected_token:
        return challenge
    return None


class WhatsAppGateway(Protocol):
    def send_text(self, to: str, text: str) -> dict: ...


@dataclass
class InboundMessage:
    message_id: str
    from_number: str
    kind: str          # text | audio
    text: str | None = None


def parse_inbound(payload: dict) -> list[InboundMessage]:
    """Extract messages from a Meta webhook payload (entry->changes->value->messages)."""
    out: list[InboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                kind = msg.get("type", "text")
                out.append(InboundMessage(
                    message_id=msg.get("id", ""),
                    from_number=msg.get("from", ""),
                    kind=kind,
                    text=(msg.get("text", {}) or {}).get("body") if kind == "text" else None))
    return out


@dataclass
class WhatsAppAdapter:
    gateway: WhatsAppGateway
    idempotency: IdempotencyGuard = field(default_factory=IdempotencyGuard)

    def handle_inbound(self, payload: dict) -> list[InboundMessage]:
        """Return the new (non-duplicate) messages to process; duplicates are dropped."""
        fresh = []
        for msg in parse_inbound(payload):
            if msg.message_id and not self.idempotency.is_duplicate(msg.message_id):
                fresh.append(msg)
        return fresh

    def reply(self, to: str, text: str) -> dict:
        return self.gateway.send_text(to, text)
