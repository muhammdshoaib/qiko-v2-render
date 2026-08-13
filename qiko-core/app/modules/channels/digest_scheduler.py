"""Inactivity digest scheduler.

Tracks the last message timestamp per (tenant, channel). On each new message it
enqueues a digest job that will be deferred by the configured inactivity window.
The job checks the latest message before running; if activity resumed, it defers
again. The queue backend is interchangeable (eager in tests, arq in production).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.core.config import get_settings
from app.integrations.clients import SlackClient
from app.modules.ai.gateway import LLMProvider
from app.modules.channels.digest import format_digest_for_slack, generate_digest
from app.modules.channels.slack_oauth import InstallationStore
from app.modules.channels.slack_store import SlackChannelStore, SlackMessage


class TaskQueue(Protocol):
    async def enqueue(self, name: str, *, defer_by: timedelta | None = None,
                      **kwargs) -> object: ...


@dataclass
class DigestScheduler:
    """Public scheduler: call on_new_message from the Slack event handler."""

    message_store: SlackChannelStore
    task_queue: TaskQueue

    async def on_new_message(self, message: SlackMessage) -> None:
        """Record the message and (re-)schedule a digest for this channel."""
        await self.message_store.add(message)

        s = get_settings()
        window = timedelta(minutes=s.slack_digest_interval_minutes)

        await self.task_queue.enqueue(
            "generate_slack_digest",
            tenant=message.tenant,
            team_id=message.team_id,
            channel_id=message.channel_id,
            defer_by=window,
        )


@dataclass
class DigestWorker:
    """The task function wired into app.tasks.jobs."""

    message_store: SlackChannelStore
    installation_store: InstallationStore
    slack_client: SlackClient | None = None
    provider: LLMProvider | None = None

    async def run(self, *, tenant: str, team_id: str, channel_id: str) -> dict:
        """Generate and post a digest if the channel has been quiet long enough."""
        s = get_settings()
        window = timedelta(minutes=s.slack_digest_interval_minutes)
        # Look back far enough to include a conversation that went quiet slightly
        # before the inactivity window; 24 hours is the practical cap.
        lookback = max(window, timedelta(hours=24))

        since = datetime.now(timezone.utc) - lookback
        messages = await self.message_store.list_since(tenant, channel_id, since)

        latest = _latest_message_ts(messages)
        now = datetime.now(timezone.utc)
        if latest is not None and (now - latest) < window:
            remaining = window - (now - latest)
            return {"deferred": True, "remaining_seconds": remaining.total_seconds()}

        if not messages:
            return {"ok": True, "messages_count": 0}

        result = generate_digest(messages, provider=self.provider)
        text = format_digest_for_slack(result, channel_id,
                                       since=_format_since(messages[0].ts))

        slack = self.slack_client or _build_slack_client(team_id, self.installation_store)
        if slack is None:
            return {"ok": False, "error": "no Slack installation for team"}

        try:
            slack.send_message(channel_id, text)
        except Exception as exc:  # pragma: no cover - network
            return {"ok": False, "error": str(exc)}

        cleared = await self.message_store.clear_channel(tenant, channel_id)
        return {"ok": True, "messages_count": cleared, "posted": True}


def _build_slack_client(team_id: str, installation_store: InstallationStore) -> SlackClient | None:
    installation = installation_store.fetch_by_team_id(team_id)
    if installation is None or not installation.bot_token:
        return None
    return SlackClient(bot_token=installation.bot_token)


def _latest_message_ts(messages: list[SlackMessage]) -> datetime | None:
    if not messages:
        return None
    best: datetime | None = None
    for m in messages:
        try:
            ts = float(m.ts)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if best is None or dt > best:
                best = dt
        except ValueError:
            continue
    return best


def _format_since(ts: str) -> str:
    try:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return ""
