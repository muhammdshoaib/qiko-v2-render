"""Gmail / Slack / ClickUp outbound integrations exposed as schema-validated agentcore tools.

Tool-calling replaces the legacy regex NL command parsers: the agent decides to call e.g.
gmail_send with structured args, and the gateway performs the side effect (heavy ops offloaded to
the arq worker). Each gateway is a protocol so the tools are testable without the network.
"""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.modules.agentcore.tools import ToolRegistry


class GmailGateway(Protocol):
    def send(self, to: str, subject: str, body: str) -> dict: ...


class SlackGateway(Protocol):
    def send_message(self, channel: str, text: str) -> dict: ...


class ClickUpGateway(Protocol):
    def create_task(self, list_id: str, name: str, description: str) -> dict: ...


class GmailSendArgs(BaseModel):
    to: str = Field(min_length=3)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


class SlackSendArgs(BaseModel):
    channel: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ClickUpTaskArgs(BaseModel):
    list_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""


def build_messaging_tools(*, gmail: GmailGateway, slack: SlackGateway, clickup: ClickUpGateway) -> ToolRegistry:
    reg = ToolRegistry()

    @reg.register("gmail_send", GmailSendArgs)
    def _gmail(a: GmailSendArgs) -> dict:
        return gmail.send(a.to, a.subject, a.body)

    @reg.register("slack_send", SlackSendArgs)
    def _slack(a: SlackSendArgs) -> dict:
        return slack.send_message(a.channel, a.text)

    @reg.register("clickup_create_task", ClickUpTaskArgs)
    def _clickup(a: ClickUpTaskArgs) -> dict:
        return clickup.create_task(a.list_id, a.name, a.description)

    return reg
