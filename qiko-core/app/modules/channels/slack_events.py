"""Slack Events API handler for the AI heads-up assistant.

Receives messages from Slack's Events API, verifies the request signature, dedups
by event id, and stores relevant channel messages in a tenant-scoped buffer. The
digest scheduler later reads the buffer and posts a summary back to the channel.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.channels.digest_scheduler import DigestScheduler
from app.modules.channels.slack_oauth import InstallationStore, SlackInstallation
from app.modules.channels.slack_store import SlackMessage
from app.modules.channels.webhooks import IdempotencyGuard, verify_slack_signature


# Hashtags the assistant explicitly watches for.
TAG_PATTERN = re.compile(r"#([a-zA-Z0-9_-]+)")
WATCHED_TAGS = {"action", "feature", "important", "decision", "question", "blocker"}


@dataclass
class SlackEventHandler:
    """Public entry point: parse and route Slack Events API payloads."""

    installation_store: InstallationStore
    scheduler: DigestScheduler
    signing_secret: str
    idempotency: IdempotencyGuard = field(default_factory=IdempotencyGuard)

    async def handle(self, payload: dict) -> dict:
        """Acknowledge the event and, for channel messages, store them for digest.

        Returns a small dict for the HTTP response body.
        """
        event_type = payload.get("type")
        if event_type == "url_verification":
            return {"challenge": payload.get("challenge", "")}

        # Event callbacks carry the payload nested under "event".
        event = payload.get("event", {})
        event_id = payload.get("event_id", "")

        if self.idempotency.is_duplicate(event_id):
            return {"ok": True, "duplicate": True}

        if event.get("type") == "message":
            await self._handle_message(event)

        if event.get("type") == "app_mention":
            await self._handle_mention(event)

        return {"ok": True}

    def verify(self, timestamp: str, body: bytes, signature: str) -> bool:
        return verify_slack_signature(self.signing_secret, timestamp, body, signature)

    async def _handle_message(self, event: dict) -> None:
        # Ignore bot messages, edits, deletions, DMs, and anything that is not a plain
        # message in a public channel. We explicitly do NOT store "message_changed".
        if event.get("bot_id") or event.get("subtype") or event.get("channel_type") != "channel":
            return

        channel = event.get("channel", "")
        text = (event.get("text") or "").strip()
        user = event.get("user", "")
        ts = event.get("ts", "")
        if not (channel and text and user and ts):
            return

        team_id = event.get("team", "")
        installation = self._resolve_installation(team_id)
        if installation is None:
            return

        tags = self._extract_tags(text)
        flagged = (
            event.get("type") == "app_mention"
            or bool(tags)
            or self._is_mention(text, installation.bot_user_id)
        )

        await self.scheduler.on_new_message(SlackMessage(
            tenant=installation.tenant or "",
            team_id=team_id,
            channel_id=channel,
            channel_type="channel",
            thread_ts=event.get("thread_ts"),
            user_id=user,
            text=text,
            ts=ts,
            flagged=flagged,
            tags=tags,
        ))

    async def _handle_mention(self, event: dict) -> None:
        # A mention in a channel is treated the same as a message, but we force the
        # flagged bit so it is captured in the next digest.
        text = (event.get("text") or "").strip()
        # Strip the bot mention and re-handle as a message.
        text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
        event["text"] = text
        await self._handle_message(event)

    def _resolve_installation(self, team_id: str) -> SlackInstallation | None:
        return self.installation_store.fetch_by_team_id(team_id)

    @staticmethod
    def _extract_tags(text: str) -> list[str]:
        tags = [m.lower() for m in TAG_PATTERN.findall(text)]
        return [t for t in tags if t in WATCHED_TAGS]

    @staticmethod
    def _is_mention(text: str, bot_user_id: str) -> bool:
        return f"<@{bot_user_id}>" in text if bot_user_id else False
