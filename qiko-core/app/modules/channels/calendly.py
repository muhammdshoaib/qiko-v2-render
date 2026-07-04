"""Calendly adapter, exposed as agentcore tools so the agent can offer slots and book meetings.
The Calendly HTTP client sits behind a gateway protocol; per-user tokens are encrypted at rest."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.modules.agentcore.tools import ToolRegistry


class CalendlyGateway(Protocol):
    def available_slots(self, event_type: str) -> list[str]: ...
    def create_booking(self, event_type: str, invitee_email: str, start: str) -> dict: ...


class SlotsArgs(BaseModel):
    event_type: str = Field(min_length=1)


class BookArgs(BaseModel):
    event_type: str = Field(min_length=1)
    invitee_email: str = Field(min_length=3)
    start: str = Field(min_length=1)


def build_calendly_tools(gateway: CalendlyGateway) -> ToolRegistry:
    reg = ToolRegistry()

    @reg.register("calendly_slots", SlotsArgs)
    def _slots(a: SlotsArgs) -> list[str]:
        return gateway.available_slots(a.event_type)

    @reg.register("calendly_book", BookArgs)
    def _book(a: BookArgs) -> dict:
        return gateway.create_booking(a.event_type, a.invitee_email, a.start)

    return reg
