"""Shared models and in-memory store for the Slack heads-up assistant."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


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


class SlackChannelStore(Protocol):
    """Tenant-scoped message buffer for one or more Slack channels."""

    async def add(self, message: SlackMessage) -> None: ...

    async def list_since(self, tenant: str, channel_id: str, since: datetime) -> list[SlackMessage]: ...

    async def clear_channel(self, tenant: str, channel_id: str) -> int: ...


@dataclass
class InMemorySlackChannelStore:
    """Dev/test in-memory store. Not multi-process safe, wiped on restart."""

    _messages: list[SlackMessage] = field(default_factory=list)

    async def add(self, message: SlackMessage) -> None:
        self._messages.append(message)

    async def list_since(self, tenant: str, channel_id: str, since: datetime) -> list[SlackMessage]:
        return [
            m for m in self._messages
            if m.tenant == tenant and m.channel_id == channel_id
            and self._ts_to_dt(m.ts) >= since
        ]

    async def clear_channel(self, tenant: str, channel_id: str) -> int:
        before = len(self._messages)
        self._messages = [
            m for m in self._messages
            if not (m.tenant == tenant and m.channel_id == channel_id)
        ]
        return before - len(self._messages)

    @staticmethod
    def _ts_to_dt(ts: str) -> datetime:
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
