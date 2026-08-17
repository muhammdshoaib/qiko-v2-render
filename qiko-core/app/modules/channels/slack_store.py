"""Shared models and the Slack adapter over the generic Signal store.

The Slack heads-up assistant still speaks `SlackMessage`, but every captured message is now
a `Signal` in the intelligence worker store. This seam lets the event handler, scheduler and
digest keep their Slack-specific shape while the storage layer is normalised.

A channel id is only unique WITHIN a workspace, so the `container` field encodes both as
`team_id/channel_id`. Two workspaces sharing one channel id therefore do not merge into a single
conversation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.modules.intelligence.models import (
    InMemorySignalStore,
    Signal,
    SignalStore,
)
from app.modules.knowledge.service import KnowledgeService

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


def slack_container(team_id: str, channel_id: str) -> str:
    return f"{team_id}/{channel_id}"


def _occurred_at_from_ts(ts: str) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


@dataclass
class SlackMessage:
    tenant: str
    agent_id: str
    team_id: str
    channel_id: str
    channel_type: str
    thread_ts: str | None
    user_id: str
    text: str
    ts: str
    kind: str = "message"
    flagged: bool = False
    tags: list[str] = field(default_factory=list)
    # Carried so the digest worker can resolve the SAME installation the event arrived for.
    # Without it an enterprise-grid workspace is unresolvable on the worker side, because the
    # installation is keyed on (team_id, enterprise_id).
    enterprise_id: str | None = None


def _slack_permalink(team_id: str, channel_id: str, ts: str) -> str:
    """A Slack web client deep-link that works for any workspace the user is signed into.

    The `ts` argument already contains the decimal separator used in Slack message timestamps.
    """
    return f"https://app.slack.com/client/{team_id}/{channel_id}/{ts}"


def _signal_text(signal: Signal) -> str:
    """Passage text used for retrieval: who, where, and what, with the source link inline."""
    lines = [f"Slack message from {signal.actor} in {signal.container}"]
    if signal.tags:
        lines.append(f"Tags: {', '.join(signal.tags)}")
    lines.append("")
    lines.append(signal.body)
    if signal.url:
        lines.append("")
        lines.append(f"Source: {signal.url}")
    return "\n".join(lines)


def _signal_doc_id(signal: Signal) -> str:
    """Use the source link as the document id when available so citations are clickable."""
    return signal.url or f"{signal.source}:{signal.external_id}"


def slack_signal_from_message(message: SlackMessage) -> Signal:
    """Convert a Slack message to the normalised Signal shape."""
    container = slack_container(message.team_id, message.channel_id)
    return Signal(
        tenant=message.tenant,
        agent_id=message.agent_id,
        source="slack",
        kind=message.kind,
        external_id=message.ts,
        container=container,
        actor=message.user_id,
        title=message.text[:200],
        body=message.text,
        occurred_at=_occurred_at_from_ts(message.ts),
        ref=None,
        url=_slack_permalink(message.team_id, message.channel_id, message.ts),
        tags=list(message.tags),
        flagged=message.flagged,
        meta={
            "team_id": message.team_id,
            "channel_id": message.channel_id,
            "channel_type": message.channel_type,
            "thread_ts": message.thread_ts,
            "enterprise_id": message.enterprise_id,
        },
    )


def slack_message_from_signal(signal: Signal) -> SlackMessage:
    """Rehydrate a SlackMessage from a Signal's meta fields."""
    meta = signal.meta or {}
    return SlackMessage(
        tenant=signal.tenant,
        agent_id=signal.agent_id,
        team_id=meta.get("team_id", ""),
        channel_id=meta.get("channel_id", ""),
        channel_type=meta.get("channel_type", "channel"),
        thread_ts=meta.get("thread_ts"),
        user_id=signal.actor,
        text=signal.body,
        ts=signal.external_id,
        kind=signal.kind or "message",
        flagged=signal.flagged,
        tags=list(signal.tags),
        enterprise_id=meta.get("enterprise_id"),
    )


class SlackChannelStore(Protocol):
    """Tenant- and agent-scoped message buffer for one or more Slack channels.

    The interface is unchanged from the original Slack-only store, but every implementation now
    delegates to a `SignalStore` and tags rows with `source=slack`.
    """

    knowledge: KnowledgeService | None

    async def add(self, message: SlackMessage) -> bool: ...

    async def list_recent(self, tenant: str, agent_id: str, team_id: str, channel_id: str,
                          since: datetime, limit: int = DEFAULT_MESSAGE_LIMIT) -> list[SlackMessage]: ...

    async def clear_channel(self, tenant: str, agent_id: str, team_id: str, channel_id: str) -> int: ...

    async def purge_older_than(self, older_than: timedelta) -> int: ...


@dataclass
class InMemorySlackChannelStore:
    """Dev/test SlackChannelStore backed by the in-memory Signal store."""

    _signal_store: SignalStore = field(default_factory=InMemorySignalStore)
    knowledge: KnowledgeService | None = None

    async def add(self, message: SlackMessage) -> bool:
        signal = slack_signal_from_message(message)
        is_new = await self._signal_store.add(signal)
        if is_new and self.knowledge is not None:
            await self.knowledge.ingest(
                signal.tenant, _signal_doc_id(signal), _signal_text(signal),
                agent_id=signal.agent_id)
        return is_new

    async def list_recent(self, tenant: str, agent_id: str, team_id: str, channel_id: str,
                          since: datetime, limit: int = DEFAULT_MESSAGE_LIMIT) -> list[SlackMessage]:
        signals = await self._signal_store.list_recent(
            tenant, agent_id, source="slack",
            container=slack_container(team_id, channel_id),
            since=since, limit=limit)
        return [slack_message_from_signal(s) for s in signals]

    async def clear_channel(self, tenant: str, agent_id: str, team_id: str, channel_id: str) -> int:
        if self.knowledge is not None:
            signals = await self._signal_store.list_recent(
                tenant, agent_id, source="slack",
                container=slack_container(team_id, channel_id),
                since=datetime.min.replace(tzinfo=timezone.utc), limit=10_000_000)
            for signal in signals:
                await self.knowledge.delete_document(
                    signal.tenant, _signal_doc_id(signal), agent_id=signal.agent_id)
        return await self._signal_store.clear(
            tenant, agent_id, source="slack",
            container=slack_container(team_id, channel_id))

    async def purge_older_than(self, older_than: timedelta) -> int:
        if self.knowledge is not None:
            signals = await self._signal_store.list_older_than(older_than, source="slack")
            for signal in signals:
                await self.knowledge.delete_document(
                    signal.tenant, _signal_doc_id(signal), agent_id=signal.agent_id)
        return await self._signal_store.purge_older_than(older_than, source="slack")

    @property
    def _messages(self) -> list[SlackMessage]:
        """Backwards-compatible view used by tests: every stored SlackMessage, newest last."""
        if isinstance(self._signal_store, InMemorySignalStore):
            return [slack_message_from_signal(s) for s in self._signal_store._signals]
        return []
