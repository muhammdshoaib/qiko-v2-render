"""Shared models and in-memory store for the Slack heads-up assistant.

Every read and every delete is keyed on (tenant, team_id, channel_id), never on
(tenant, channel_id). A channel id is only unique WITHIN a workspace, so dropping team_id
would merge two workspaces that happen to share one into a single digest, and post it with
whichever workspace's bot token was resolved first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

# The digest only ever needs the tail of a conversation. Capping the read bounds both the
# prompt handed to the model and the memory held while building it (LLM10 / API4).
DEFAULT_MESSAGE_LIMIT = 200


def slack_ts(moment: datetime) -> str:
    """Render a datetime in Slack's `ts` format: ten digits, a dot, six digits.

    Fixed width is the point. It makes lexicographic order equal numeric order, so the SQL store
    can range-scan and sort on the indexed `ts` column directly instead of casting it, and the two
    store implementations select exactly the same messages.
    """
    return f"{moment.timestamp():017.6f}"


@dataclass
class SlackMessage:
    tenant: str
    team_id: str
    channel_id: str
    channel_type: str
    thread_ts: str | None
    user_id: str
    text: str
    ts: str
    flagged: bool = False
    tags: list[str] = field(default_factory=list)
    # Carried so the digest worker can resolve the SAME installation the event arrived for.
    # Without it an enterprise-grid workspace is unresolvable on the worker side, because the
    # installation is keyed on (team_id, enterprise_id).
    enterprise_id: str | None = None


class SlackChannelStore(Protocol):
    """Tenant-scoped message buffer for one or more Slack channels."""

    async def add(self, message: SlackMessage) -> None: ...

    async def list_recent(self, tenant: str, team_id: str, channel_id: str, since: datetime,
                          limit: int = DEFAULT_MESSAGE_LIMIT) -> list[SlackMessage]: ...

    async def clear_channel(self, tenant: str, team_id: str, channel_id: str) -> int: ...


@dataclass
class InMemorySlackChannelStore:
    """Dev/test in-memory store. Not multi-process safe, wiped on restart."""

    _messages: list[SlackMessage] = field(default_factory=list)

    async def add(self, message: SlackMessage) -> None:
        self._messages.append(message)

    async def list_recent(self, tenant: str, team_id: str, channel_id: str, since: datetime,
                          limit: int = DEFAULT_MESSAGE_LIMIT) -> list[SlackMessage]:
        # Compared and sorted exactly as the SQL store does, so the implementation the tests drive
        # and the one that ships cannot select different messages.
        cutoff = slack_ts(since)
        matching = [m for m in self._messages
                    if self._same_channel(m, tenant, team_id, channel_id) and m.ts >= cutoff]
        matching.sort(key=lambda m: m.ts)
        # Newest `limit` messages, returned oldest-first so the transcript reads in order.
        return matching[-limit:]

    async def clear_channel(self, tenant: str, team_id: str, channel_id: str) -> int:
        before = len(self._messages)
        self._messages = [m for m in self._messages
                          if not self._same_channel(m, tenant, team_id, channel_id)]
        return before - len(self._messages)

    @staticmethod
    def _same_channel(message: SlackMessage, tenant: str, team_id: str, channel_id: str) -> bool:
        return (message.tenant == tenant and message.team_id == team_id
                and message.channel_id == channel_id)
