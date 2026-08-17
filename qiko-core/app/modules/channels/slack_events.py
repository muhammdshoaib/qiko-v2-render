"""Slack Events API handler for the AI heads-up assistant.

Receives messages from Slack's Events API, verifies the request signature, dedups
by event id, and stores relevant channel messages in a tenant-scoped buffer. The
digest scheduler later reads the buffer and posts a summary back to the channel.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

from app.modules.channels.digest_scheduler import DigestScheduler
from app.modules.channels.slack_oauth import InstallationStore, SlackInstallation
from app.modules.channels.slack_store import SlackMessage
from app.modules.channels.webhooks import IdempotencyGuard, verify_slack_signature

logger = logging.getLogger(__name__)

# Hashtags the assistant explicitly watches for.
TAG_PATTERN = re.compile(r"#([a-zA-Z0-9_-]+)")
WATCHED_TAGS = {"action", "feature", "important", "decision", "question", "blocker"}

# One Slack message is capped at 40k characters, and the digest window holds many of them.
# Truncating on the way IN bounds both the row and every prompt built from it (LLM10).
MAX_MESSAGE_CHARS = 4_000


@dataclass
class SlackEventHandler:
    """Public entry point: parse and route Slack Events API payloads."""

    installation_store: InstallationStore
    scheduler: DigestScheduler
    signing_secret: str
    agent_store: object | None = None
    idempotency: IdempotencyGuard = field(default_factory=IdempotencyGuard)

    async def handle(self, payload: dict) -> dict:
        """Acknowledge the event and, for channel messages, store them for digest.

        Returns a small dict for the HTTP response body.
        """
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}

        event = payload.get("event", {})
        event_id = payload.get("event_id", "")

        # A payload with no event id cannot be deduped. Seeding the guard with "" would make the
        # FIRST such payload win and silently drop every later one, which is the opposite of the
        # intended behaviour, so an id-less event is processed and recorded instead.
        if not event_id:
            logger.warning("slack event without event_id; cannot dedupe",
                           extra={"source": "channels.slack"})
        elif self.idempotency.is_duplicate(event_id):
            return {"ok": True, "duplicate": True}

        # The workspace comes from the TOP-LEVEL payload, which identifies the installation the
        # event was delivered for. event.team is the message AUTHOR's workspace, which differs in
        # a Slack Connect channel and would attribute the message to the wrong tenant.
        team_id = payload.get("team_id", "")
        enterprise_id = (payload.get("enterprise_id")
                         or (payload.get("enterprise") or {}).get("id") or None)

        event_type = event.get("type")
        if event_type not in {"message", "app_mention"}:
            return {"ok": True}

        # The production installation store is synchronous (see app/db/sync_stores.py), so the
        # lookup goes to a thread: a blocking DB round trip here would stall the event loop on
        # every inbound Slack event.
        installation = await asyncio.to_thread(
            self.installation_store.fetch_by_workspace, team_id, enterprise_id)
        if installation is None:
            # Not an error the caller can fix, and not something to be silent about: it is also
            # what an ambiguous or unowned installation looks like (see fetch_by_workspace).
            logger.warning("slack event for an unresolvable workspace; dropped",
                           extra={"source": "channels.slack", "team_id": team_id,
                                  "event_id": event_id})
            return {"ok": True, "dropped": True}

        if not installation.tenant or not installation.worker_id:
            logger.warning("slack event for an installation with no tenant/worker; dropped",
                           extra={"source": "channels.slack", "team_id": team_id,
                                  "event_id": event_id})
            return {"ok": True, "dropped": True}

        await self._handle_event(event, event_type, installation, team_id, enterprise_id)
        return {"ok": True}

    def verify(self, timestamp: str, body: bytes, signature: str) -> bool:
        return verify_slack_signature(self.signing_secret, timestamp, body, signature)

    async def _handle_event(self, event: dict, event_type: str,
                            installation: SlackInstallation, team_id: str,
                            enterprise_id: str | None) -> None:
        text = (event.get("text") or "").strip()
        if event_type == "app_mention":
            # An app_mention carries no channel_type, so it is set explicitly rather than being
            # filtered out below. The bot mention itself is stripped from the stored text.
            text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
            channel_type = "channel"
            kind = "mention"
        else:
            # Ignore bot messages, edits, deletions, DMs, and anything that is not a plain
            # message in a public channel. "message_changed" is deliberately NOT stored.
            if event.get("bot_id") or event.get("subtype") or event.get("channel_type") != "channel":
                return
            channel_type = "channel"
            kind = "message"

        channel = event.get("channel", "")
        user = event.get("user", "")
        ts = event.get("ts", "")
        if not (channel and text and user and ts):
            return

        if self.agent_store is not None:
            agent = await self.agent_store.get(installation.tenant, installation.worker_id)
            watched = (agent.config or {}).get("slack_watched_channels") or [] if agent else []
            if channel not in watched:
                return

        tags = self._extract_tags(text)
        flagged = (event_type == "app_mention" or bool(tags)
                   or self._is_mention(text, installation.bot_user_id))

        await self.scheduler.on_new_message(SlackMessage(
            tenant=installation.tenant,
            agent_id=installation.worker_id,
            team_id=team_id,
            channel_id=channel,
            channel_type=channel_type,
            thread_ts=event.get("thread_ts"),
            user_id=user,
            text=text[:MAX_MESSAGE_CHARS],
            ts=ts,
            kind=kind,
            flagged=flagged,
            tags=tags,
            enterprise_id=enterprise_id,
        ))

    @staticmethod
    def _extract_tags(text: str) -> list[str]:
        tags = [m.lower() for m in TAG_PATTERN.findall(text)]
        return [t for t in tags if t in WATCHED_TAGS]

    @staticmethod
    def _is_mention(text: str, bot_user_id: str) -> bool:
        return f"<@{bot_user_id}>" in text if bot_user_id else False
