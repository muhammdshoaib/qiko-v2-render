"""Interakt (WhatsApp BSP) adapter.

Unlike Meta's native Cloud API (see channels/whatsapp.py), Interakt's public API exposes no
free-text send endpoint at all, only pre-approved Template Message Send (confirmed against
interakt.shop's own docs, JM2-1024/1027 research). A worker cannot just "reply with generated
text" here: reply_mode drives what actually happens, per the confirmed jm-backend contract
(JM2-1066): an approved template with filled parameters, a drafted reply left for a human agent
to send manually through Interakt's own inbox, or a straight handoff with nothing sent
automatically at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


@dataclass
class InboundInteraktMessage:
    message_id: str
    phone_number: str
    text: str


def parse_inbound(payload: dict) -> InboundInteraktMessage | None:
    """Extract a text message from an Interakt 'message_received' webhook payload (confirmed
    shape against interakt.shop's own docs, JM2-1024 research). Returns None for any other
    event type (e.g. message_api_sent/delivered/read/failed) or a non-text message (media),
    which the caller should ack with 200 and otherwise ignore."""
    if payload.get("type") != "message_received":
        return None
    data = payload.get("data") or {}
    message = data.get("message") or {}
    if message.get("message_content_type") != "Text":
        return None
    customer = data.get("customer") or {}
    message_id = message.get("id")
    phone_number = customer.get("channel_phone_number")
    text = message.get("message")
    if not message_id or not phone_number or not text:
        return None
    return InboundInteraktMessage(message_id=message_id, phone_number=phone_number, text=text)


class ReplyMode(str, Enum):
    template = "template"
    draft_for_agent = "draft_for_agent"
    handoff = "handoff"


class InteraktSendError(Exception):
    pass


class InteraktClient(Protocol):
    def send_template(self, to: str, template_name: str, params: list[str]) -> dict: ...


@dataclass(frozen=True)
class WorkerReply:
    """What the worker decided to do with a generated turn."""

    reply_mode: ReplyMode
    template_name: str | None = None
    template_params: tuple[str, ...] = field(default_factory=tuple)
    draft_text: str | None = None
    handoff_reason: str | None = None

    def __post_init__(self) -> None:
        if self.reply_mode is ReplyMode.template and not self.template_name:
            raise ValueError("template reply_mode requires template_name")
        if self.reply_mode is ReplyMode.draft_for_agent and not self.draft_text:
            raise ValueError("draft_for_agent reply_mode requires draft_text")


@dataclass
class InteraktGateway:
    client: InteraktClient

    def send(self, to: str, reply: WorkerReply) -> dict:
        """Execute the worker's chosen reply_mode. template is the only mode Interakt's public API
        can actually deliver; draft_for_agent and handoff never touch the API, since there is
        nothing it can send on our behalf for either. The caller (channels router) surfaces those
        to a human agent instead."""
        if reply.reply_mode is ReplyMode.template:
            return self.client.send_template(to, reply.template_name, list(reply.template_params))
        if reply.reply_mode is ReplyMode.draft_for_agent:
            return {"status": "drafted", "requiresHumanSend": True, "draftText": reply.draft_text}
        if reply.reply_mode is ReplyMode.handoff:
            return {"status": "handoff", "reason": reply.handoff_reason}
        raise InteraktSendError(f"unknown reply_mode: {reply.reply_mode}")
