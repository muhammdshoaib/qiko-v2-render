import pytest

from app.modules.agentcore.tools import ToolError
from app.modules.channels.messaging import build_messaging_tools


class FakeGmail:
    def send(self, to, subject, body):
        return {"sent": True, "to": to, "subject": subject}


class FakeSlack:
    def send_message(self, channel, text):
        return {"ok": True, "channel": channel, "text": text}


class FakeClickUp:
    def create_task(self, list_id, name, description):
        return {"id": "task_1", "list_id": list_id, "name": name}


def _reg():
    return build_messaging_tools(gmail=FakeGmail(), slack=FakeSlack(), clickup=FakeClickUp())


def test_messaging_tools_registered():
    assert _reg().names() == ["clickup_create_task", "gmail_send", "slack_send"]


async def test_tools_invoke_gateways():
    reg = _reg()
    assert (await reg.invoke("gmail_send", {"to": "a@x.com", "subject": "Hi", "body": "Hello"}))["sent"] is True
    assert (await reg.invoke("slack_send", {"channel": "#general", "text": "Hi"}))["channel"] == "#general"
    assert (await reg.invoke("clickup_create_task", {"list_id": "L1", "name": "Do it"}))["id"] == "task_1"


async def test_messaging_args_validated():
    reg = _reg()
    with pytest.raises(ToolError):
        await reg.invoke("gmail_send", {"to": "a@x.com", "subject": "", "body": "x"})  # empty subject
    with pytest.raises(ToolError):
        await reg.invoke("slack_send", {"channel": "#g"})  # missing text
