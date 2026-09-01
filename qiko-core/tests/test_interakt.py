import pytest

from app.modules.channels.interakt import InteraktGateway, ReplyMode, WorkerReply


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
