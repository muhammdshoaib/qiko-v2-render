import pytest

from app.core.crypto import decrypt, encrypt
from app.modules.agentcore.tools import ToolError
from app.modules.channels.calendly import build_calendly_tools


def test_token_encryption_roundtrip():
    token = "cal_live_secret_123"
    enc = encrypt(token)
    assert enc != token and decrypt(enc) == token


class FakeCalendly:
    def available_slots(self, event_type):
        return ["2026-07-10T09:00", "2026-07-10T10:00"]

    def create_booking(self, event_type, invitee_email, start):
        return {"booked": True, "event_type": event_type, "invitee": invitee_email, "start": start}


async def test_calendly_tools_slots_and_book():
    reg = build_calendly_tools(FakeCalendly())
    assert reg.names() == ["calendly_book", "calendly_slots"]
    slots = await reg.invoke("calendly_slots", {"event_type": "intro-call"})
    assert len(slots) == 2
    booking = await reg.invoke("calendly_book", {"event_type": "intro-call",
                                                 "invitee_email": "a@x.com", "start": slots[0]})
    assert booking["booked"] is True and booking["invitee"] == "a@x.com"


async def test_calendly_tool_args_validated():
    reg = build_calendly_tools(FakeCalendly())
    with pytest.raises(ToolError):
        await reg.invoke("calendly_book", {"event_type": "x", "invitee_email": "a@x.com"})  # missing start
