"""Tests for the Slack heads-up digest generator and worker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.modules.ai.gateway import LLMResponse
from app.modules.channels.digest import DigestResult, build_digest_prompt, format_digest_for_slack, generate_digest
from app.modules.channels.digest_scheduler import DigestWorker
from app.modules.channels.slack_oauth import SlackInstallation
from app.modules.channels.slack_store import InMemorySlackChannelStore, SlackMessage


def _msg(text: str, ts: str, tenant: str = "t1", channel: str = "C1",
         user: str = "U1", tags=None, flagged: bool = False) -> SlackMessage:
    return SlackMessage(
        tenant=tenant,
        team_id="T1",
        channel_id=channel,
        channel_type="channel",
        thread_ts=None,
        user_id=user,
        text=text,
        ts=ts,
        flagged=flagged,
        tags=tags or [],
    )


def test_digest_prompt_includes_messages():
    messages = [
        _msg("what is the launch date?", "1503435956.000247"),
        _msg("fix pricing page #action", "1503435957.000248"),
    ]
    prompt = build_digest_prompt(messages)
    assert "launch date" in prompt
    assert "#action" in prompt
    assert "Return valid JSON only" in prompt


def test_generate_digest_parses_json():
    messages = [_msg("do it", "1503435956.000247")]
    raw = '{"summary": " discussed action", "action_items": [{"text": "do it", "owner": "U1", "urgency": "high"}], "tone": "calm"}'
    provider = Mock()
    provider.generate.return_value = LLMResponse(text=raw)
    result = generate_digest(messages, provider=provider)
    assert result.summary == " discussed action"
    assert len(result.action_items) == 1
    assert result.action_items[0]["text"] == "do it"


def test_generate_digest_handles_markdown_fences():
    messages = [_msg("hello", "1503435956.000247")]
    raw = '```json\n{"summary": "hello summary", "action_items": [], "tone": "calm"}\n```'
    provider = Mock()
    provider.generate.return_value = LLMResponse(text=raw)
    result = generate_digest(messages, provider=provider)
    assert result.summary == "hello summary"


def test_format_digest_includes_sections():
    result = DigestResult(
        summary="A discussion happened",
        action_items=[{"text": "fix pricing", "owner": "U1", "urgency": "high"}],
        decisions=[{"text": "use Bedrock"}],
        tone="at-risk",
    )
    text = format_digest_for_slack(result, "C1")
    assert "A discussion happened" in text
    assert "fix pricing" in text
    assert "use Bedrock" in text
    assert "at-risk" in text


@pytest.mark.asyncio
async def test_digest_worker_defer_while_active():
    now = datetime.now(timezone.utc)
    recent_ts = str(now.timestamp())
    store = InMemorySlackChannelStore()
    await store.add(_msg("active", recent_ts))
    worker = DigestWorker(
        message_store=store,
        installation_store=Mock(),
        provider=Mock(),
    )
    result = await worker.run(tenant="t1", team_id="T1", channel_id="C1")
    assert result["deferred"] is True


@pytest.mark.asyncio
async def test_digest_worker_posts_and_clears():
    now = datetime.now(timezone.utc)
    old_ts = str((now - timedelta(hours=2)).timestamp())
    store = InMemorySlackChannelStore()
    await store.add(_msg("what about pricing?", old_ts))
    installation = SlackInstallation(
        team_id="T1",
        bot_token="xoxb-fake",
        bot_user_id="U1",
        tenant="t1",
        worker_id="w1",
    )
    inst_store = Mock()
    inst_store.fetch_by_team_id.return_value = installation
    slack_client = Mock()
    slack_client.send_message = Mock()
    worker = DigestWorker(
        message_store=store,
        installation_store=inst_store,
        slack_client=slack_client,
        provider=Mock(generate=Mock(return_value=LLMResponse(
            text='{"summary": "discussed pricing", "action_items": [], "tone": "calm"}',
        ))),
    )
    result = await worker.run(tenant="t1", team_id="T1", channel_id="C1")
    assert result["ok"] is True
    assert result["posted"] is True
    slack_client.send_message.assert_called_once()
    assert len(store._messages) == 0
