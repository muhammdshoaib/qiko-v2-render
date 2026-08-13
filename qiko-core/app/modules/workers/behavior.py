from __future__ import annotations

from typing import TypedDict


BEHAVIOR_FIELDS = (
    ("prompts", "Prompts"),
    ("rules", "Rules"),
    ("guardrails", "Guardrails"),
)
BEHAVIOR_CONFIG_KEYS = frozenset(key for key, _heading in BEHAVIOR_FIELDS)
BEHAVIOR_MAX_ENTRIES = 50
BEHAVIOR_MAX_ID = 128
BEHAVIOR_MAX_TITLE = 255
BEHAVIOR_MAX_CONTENT = 4000
BEHAVIOR_MAX_TOTAL = 20_000

_ALLOWED_ENTRY_KEYS = frozenset({"id", "title", "content", "description"})


class BehaviorEntry(TypedDict):
    id: str
    title: str
    content: str


def _canonical_entry(raw: object) -> tuple[BehaviorEntry, int]:
    if isinstance(raw, str):
        if len(raw) > BEHAVIOR_MAX_CONTENT:
            raise ValueError
        entry_id, title, content = "", "", raw
    elif isinstance(raw, dict):
        if set(raw) - _ALLOWED_ENTRY_KEYS:
            raise ValueError
        entry_id = raw.get("id", "")
        title = raw.get("title", "")
        raw_content = raw.get("content")
        description = raw.get("description")
        if not isinstance(entry_id, str) or not isinstance(title, str):
            raise ValueError
        if "description" in raw and not isinstance(description, str):
            raise ValueError
        if isinstance(raw_content, str):
            content = raw_content
        elif raw_content is None and isinstance(description, str):
            content = description
        elif "content" not in raw and "description" not in raw:
            content = ""
        else:
            raise ValueError
        if (len(entry_id) > BEHAVIOR_MAX_ID or len(title) > BEHAVIOR_MAX_TITLE or
                len(content) > BEHAVIOR_MAX_CONTENT):
            raise ValueError
    else:
        raise ValueError

    entry = {"id": entry_id.strip(), "title": title.strip(), "content": content.strip()}
    if not entry["title"] and not entry["content"]:
        raise ValueError
    return entry, len(title) + len(content)


def canonicalize_behavior_entries(value: object, *, strict: bool) -> list[BehaviorEntry]:
    if isinstance(value, (str, dict)):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        if strict:
            raise ValueError
        return []

    if strict and len(values) > BEHAVIOR_MAX_ENTRIES:
        raise ValueError

    entries: list[BehaviorEntry] = []
    total = 0
    for raw in values[:BEHAVIOR_MAX_ENTRIES]:
        try:
            entry, entry_size = _canonical_entry(raw)
        except ValueError:
            if strict:
                raise
            continue
        if total + entry_size > BEHAVIOR_MAX_TOTAL:
            if strict:
                raise ValueError
            continue
        entries.append(entry)
        total += entry_size
    return entries
