"""AI digest generation for captured Slack conversations.

Reads a window of SlackMessage objects, prompts Claude on Bedrock for a structured summary,
and formats the result as a Slack mrkdwn post.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.modules.ai.gateway import LLMProvider, get_provider
from app.modules.channels.slack_store import SlackMessage


@dataclass
class DigestResult:
    summary: str = ""
    action_items: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    unanswered_questions: list[dict] = field(default_factory=list)
    feature_flags: list[dict] = field(default_factory=list)
    blockers: list[dict] = field(default_factory=list)
    tone: str = "calm"


def _ts_to_time(ts: str) -> str:
    try:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return dt.strftime("%H:%M")
    except ValueError:
        return "?"


def _format_messages(messages: list[SlackMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        time = _ts_to_time(m.ts)
        tags = " ".join(f"#{t}" for t in m.tags) if m.tags else ""
        lines.append(f"[{time}] <@{m.user_id}>: {m.text} {tags}".strip())
    return "\n".join(lines)


def build_digest_prompt(messages: list[SlackMessage]) -> str:
    transcript = _format_messages(messages)
    return (
        "You are an executive assistant summarising a Slack channel for a busy team. "
        "Read the following messages and return a structured JSON object with no markdown and "
        "no preamble.\n\n"
        "Transcript:\n" + transcript + "\n\n"
        "Analyse the conversation and produce this exact JSON shape:\n"
        "{\n"
        '  "summary": "one short paragraph of what was discussed",\n'
        '  "action_items": [\n'
        '    {"text": "what needs doing", "owner": "@user_id or null", "urgency": "low|medium|high"}\n'
        '  ],\n'
        '  "decisions": [\n'
        '    {"text": "decision made"}\n'
        '  ],\n'
        '  "unanswered_questions": [\n'
        '    {"text": "question still open"}\n'
        '  ],\n'
        '  "feature_flags": [\n'
        '    {"text": "feature / product / launch item flagged with #feature or #important", "tags": ["feature"]}\n'
        '  ],\n'
        '  "blockers": [\n'
        '    {"text": "thing blocking progress"}\n'
        '  ],\n'
        '  "tone": "calm|tense|at-risk"\n'
        "}\n\n"
        "Rules:\n"
        "- action_items, decisions, unanswered_questions, feature_flags and blockers may be empty arrays.\n"
        "- owner is the Slack user id if it can be inferred, otherwise null.\n"
        "- feature_flags are only items explicitly tagged #feature, #important, #action or that are clearly product/launch decisions needing follow-up.\n"
        "- Keep each text field under 160 characters.\n"
        "- Return valid JSON only."
    )


def _clean_json(text: str) -> str:
    """Strip any accidental markdown fences or preamble from the LLM reply."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_digest(raw: str) -> DigestResult:
    text = _clean_json(raw)
    # If the model did not emit an object, return an empty result rather than crash.
    if not text.startswith("{"):
        return DigestResult(summary=text[:500])
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return DigestResult(summary=text[:500])

    def _items(key: str) -> list[dict]:
        value = data.get(key)
        if not isinstance(value, list):
            return []
        return [i for i in value if isinstance(i, dict) and i.get("text")]

    return DigestResult(
        summary=_coerce_str(data.get("summary"), "")[:500],
        action_items=_items("action_items"),
        decisions=_items("decisions"),
        unanswered_questions=_items("unanswered_questions"),
        feature_flags=_items("feature_flags"),
        blockers=_items("blockers"),
        tone=_coerce_str(data.get("tone"), "calm"),
    )


def _coerce_str(value, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def generate_digest(messages: list[SlackMessage],
                    provider: LLMProvider | None = None) -> DigestResult:
    """Send the transcript to the configured AI provider and return a structured digest."""
    if not messages:
        return DigestResult(summary="No messages to summarise.")

    prompt = build_digest_prompt(messages)
    llm = (provider or get_provider())
    response = llm.generate(prompt, prefill="{", temperature=0.2)
    return _parse_digest(response.text)


def _link_to_channel(channel_id: str, text: str) -> str:
    return f"<#{channel_id}|{channel_id}>" if channel_id else text


def format_digest_for_slack(result: DigestResult, channel_id: str, since: str = "") -> str:
    """Convert a DigestResult to a Slack mrkdwn message."""
    lines: list[str] = []
    header = f"*Heads-up for {_link_to_channel(channel_id, 'this channel')}*"
    if since:
        header += f" _since {since}_"
    lines.append(header)
    lines.append(result.summary or "_No new activity to report._")

    def _section(title: str, items: list[dict], emoji: str) -> None:
        if not items:
            return
        lines.append(f"\n{emoji} *{title}*")
        for i, item in enumerate(items, 1):
            text = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
            owner = item.get("owner")
            urgency = item.get("urgency")
            suffix = ""
            if owner:
                suffix += f"  ({owner}"
                if urgency:
                    suffix += f", {urgency}"
                suffix += ")"
            elif urgency:
                suffix = f"  ({urgency})"
            lines.append(f"{i}. {text}{suffix}")

    _section("Action items", result.action_items, ":white_check_mark:")
    _section("Decisions", result.decisions, ":speech_balloon:")
    _section("Unanswered questions", result.unanswered_questions, ":question:")
    _section("Flagged / important", result.feature_flags, ":fire:")
    _section("Blockers", result.blockers, ":octagonal_sign:")

    if result.tone and result.tone != "calm":
        lines.append(f"\n_Tone: {result.tone}_")

    return "\n".join(lines)
