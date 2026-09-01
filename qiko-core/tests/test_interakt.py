import pytest

from app.modules.channels.interakt import InteraktGateway, ReplyMode, WorkerReply, parse_inbound


class FakeInteraktClient:
    def __init__(self):
        self.sent = []

    def send_template(self, to, template_name, params):
        self.sent.append((to, template_name, params))
        return {"ok": True}


def test_template_reply_calls_send_template():
    client = FakeInteraktClient()
    reply = WorkerReply(reply_mode=ReplyMode.template, template_name="booking_confirm",
                        template_params=("Jane", "3 Sep"))
    result = InteraktGateway(client).send("15551234", reply)
    assert client.sent == [("15551234", "booking_confirm", ["Jane", "3 Sep"])]
    assert result == {"ok": True}


def test_draft_for_agent_never_calls_the_api():
    client = FakeInteraktClient()
    reply = WorkerReply(reply_mode=ReplyMode.draft_for_agent, draft_text="Suggested reply: ...")
    result = InteraktGateway(client).send("15551234", reply)
    assert client.sent == []
    assert result == {"status": "drafted", "requiresHumanSend": True, "draftText": "Suggested reply: ..."}


def test_handoff_never_calls_the_api():
    client = FakeInteraktClient()
    reply = WorkerReply(reply_mode=ReplyMode.handoff, handoff_reason="asked for legal advice")
    result = InteraktGateway(client).send("15551234", reply)
    assert client.sent == []
    assert result == {"status": "handoff", "reason": "asked for legal advice"}


def test_template_reply_requires_a_template_name():
    with pytest.raises(ValueError):
        WorkerReply(reply_mode=ReplyMode.template)


def test_draft_for_agent_requires_draft_text():
    with pytest.raises(ValueError):
        WorkerReply(reply_mode=ReplyMode.draft_for_agent)


def _message_received(*, message="Hi there", message_id="msg-1", content_type="Text",
                      phone="447700900000"):
    return {
        "version": "1.0",
        "timestamp": "2026-08-28T10:00:00.000000",
        "type": "message_received",
        "data": {
            "customer": {"id": "cust-1", "channel_phone_number": phone, "traits": {}},
            "message": {
                "id": message_id,
                "chat_message_type": "CustomerMessage",
                "message_status": "Sent",
                "received_at_utc": "2026-08-28T10:00:00.000000",
                "is_template_message": False,
                "message_content_type": content_type,
                "message": message,
                "meta_data": {},
            },
        },
    }


def test_parse_inbound_extracts_text_message():
    parsed = parse_inbound(_message_received())
    assert parsed is not None
    assert parsed.message_id == "msg-1"
    assert parsed.phone_number == "447700900000"
    assert parsed.text == "Hi there"


def test_parse_inbound_ignores_non_text_content():
    parsed = parse_inbound(_message_received(content_type="Image"))
    assert parsed is None


def test_parse_inbound_ignores_a_non_message_received_event():
    payload = _message_received()
    payload["type"] = "message_api_sent"
    assert parse_inbound(payload) is None
