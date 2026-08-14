"""Inactivity digest scheduler.

On every captured message the scheduler stores it and enqueues a digest job deferred by the
inactivity window. The job re-checks the newest message before doing any work, so a channel that
is still active defers again instead of digesting a live conversation.

Ordering inside the job is deliberate. The Slack bot token is resolved BEFORE the model is called:
resolving it afterwards meant an unresolvable workspace raised after the spend, and arq's retries
then paid for the same digest three times and still posted nothing.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.core.config import get_settings
from app.core.tenancy import reset_tenant, set_tenant
from app.integrations.clients import SlackClient
from app.modules.ai import usage
from app.modules.ai.gateway import LLMProvider
from app.modules.channels.digest import (
    DigestUnavailable,
    format_digest_for_slack,
    generate_digest,
)
from app.modules.channels.slack_oauth import InstallationStore
from app.modules.channels.slack_store import (
    DEFAULT_MESSAGE_LIMIT,
    SlackChannelStore,
    SlackMessage,
)

logger = logging.getLogger(__name__)

# How far back a digest may read, independent of the inactivity window. Bounds the query and the
# amount of personal data that can end up in one prompt.
MAX_LOOKBACK = timedelta(hours=24)


class TaskQueue(Protocol):
    async def enqueue(self, name: str, *, defer_by: timedelta | None = None,
                      **kwargs) -> object: ...


@dataclass
class DigestScheduler:
    """Public scheduler: call on_new_message from the Slack event handler."""

    message_store: SlackChannelStore
    task_queue: TaskQueue

    async def on_new_message(self, message: SlackMessage) -> None:
        """Record the message and (re-)schedule a digest for its channel."""
        await self.message_store.add(message)
        await self.task_queue.enqueue(
            "generate_slack_digest",
            tenant=message.tenant,
            team_id=message.team_id,
            channel_id=message.channel_id,
            defer_by=_window(),
        )


@dataclass
class DigestWorker:
    """The task function wired into app.tasks.jobs."""

    message_store: SlackChannelStore
    installation_store: InstallationStore | None = None
    slack_client: SlackClient | None = None
    provider: LLMProvider | None = None
    cost_guard: object | None = None
    usage_store: object | None = None

    async def run(self, *, tenant: str, team_id: str, channel_id: str) -> dict:
        """Generate and post a digest if the channel has been quiet long enough."""
        window = _window()
        since = datetime.now(timezone.utc) - max(window, MAX_LOOKBACK)
        messages = await self.message_store.list_recent(
            tenant, team_id, channel_id, since, limit=DEFAULT_MESSAGE_LIMIT)

        latest = _latest_message_ts(messages)
        now = datetime.now(timezone.utc)
        if latest is not None and (now - latest) < window:
            return {"deferred": True,
                    "remaining_seconds": (window - (now - latest)).total_seconds()}
        if not messages:
            return {"ok": True, "messages_count": 0}

        # Resolve the destination BEFORE spending on the model (see the module docstring).
        slack = self.slack_client or self._resolve_slack_client(team_id)
        if slack is None:
            logger.warning("slack digest has no usable installation; not generating",
                           extra={"source": "channels.digest", "team_id": team_id})
            return {"ok": False, "error": "no Slack installation for team"}

        # A tenant that has reached its AI spend cap does not get an unmetered background job.
        if self.cost_guard is not None:
            decision = await self.cost_guard.check(tenant)
            if not decision.allowed:
                logger.warning("slack digest skipped: AI cost cap reached",
                               extra={"source": "channels.digest", "tenant": tenant})
                return {"ok": False, "error": "cost cap reached"}

        try:
            result = await self._generate(tenant, messages)
        except DigestUnavailable as exc:
            # The buffer is deliberately NOT cleared: the next run should try these messages again.
            logger.warning("slack digest unavailable; nothing posted",
                           extra={"source": "channels.digest", "reason": str(exc)})
            return {"ok": False, "error": "digest unavailable"}

        text = format_digest_for_slack(result, channel_id, since=_format_since(messages[0].ts))
        try:
            await asyncio.to_thread(slack.send_message, channel_id, text)
        except Exception:
            logger.warning("slack digest post failed", exc_info=True,
                           extra={"source": "channels.digest", "team_id": team_id})
            return {"ok": False, "error": "slack post failed"}

        cleared = await self.message_store.clear_channel(tenant, team_id, channel_id)
        return {"ok": True, "messages_count": cleared, "posted": True}

    async def _generate(self, tenant: str, messages: list[SlackMessage]):
        """Run the model call with the tenant bound and its token spend accounted for.

        Without the tenant context and usage scope the spend is recorded outside a scope and
        dropped, so this path would consume Bedrock tokens that never appear in AI usage or count
        towards the tenant's cap. The blocking boto3 call goes to a thread so it cannot stall the
        event loop of whichever process runs the job.
        """
        token = set_tenant(tenant)
        try:
            with usage.scope() as events:
                try:
                    return await asyncio.to_thread(generate_digest, messages, self.provider)
                finally:
                    await usage.flush(self.usage_store, events)
        finally:
            reset_tenant(token)

    def _resolve_slack_client(self, team_id: str) -> SlackClient | None:
        if self.installation_store is None:
            logger.error("slack digest worker has no installation store wired",
                         extra={"source": "channels.digest"})
            return None
        installation = self.installation_store.fetch_by_workspace(team_id)
        if installation is None or not installation.bot_token:
            return None
        return SlackClient(bot_token=installation.bot_token)


def _window() -> timedelta:
    return timedelta(minutes=get_settings().slack_digest_interval_minutes)


def _latest_message_ts(messages: list[SlackMessage]) -> datetime | None:
    stamps = []
    for m in messages:
        try:
            stamps.append(datetime.fromtimestamp(float(m.ts), tz=timezone.utc))
        except ValueError:
            continue
    return max(stamps) if stamps else None


def _format_since(ts: str) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return ""
