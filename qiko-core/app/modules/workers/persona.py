"""Synthesize a per-worker persona (identity) prompt from the Train wizard's config.

QIK-315: every worker used to fall back to the generic bid-response-writer voice because the wizard
writes expertise/tone/rules to config but never a `system_prompt`. We build the identity here from
those fields so each worker sounds like itself. This is ONLY the identity -- the generator always
appends the shared output contract (JSON shape), so structured answering is never lost.
"""
from __future__ import annotations

from app.modules.workers.behavior import BEHAVIOR_FIELDS, canonicalize_behavior_entries


GROUNDING_INSTRUCTION = ("Answer using ONLY the supplied evidence; do not invent facts, dates, names, or "
                         "figures. If the evidence is insufficient, say so.")


def synthesize_behavior(config: dict) -> str | None:
    sections = []
    for key, heading in BEHAVIOR_FIELDS:
        entries = canonicalize_behavior_entries(config.get(key), strict=False)
        rendered = [f'{entry["title"]}: {entry["content"]}'
                    if entry["title"] and entry["content"] else entry["title"] or entry["content"]
                    for entry in entries]
        if rendered:
            sections.append(f"{heading}:\n" + "\n".join(f"- {entry}" for entry in rendered))
    return "\n\n".join(sections) or None


def synthesize_persona(config: dict) -> str | None:
    """Return an identity prompt built from the worker's config, or None when there is no meaningful
    identity config (so the worker keeps the default identity). Never includes secrets: it only reads
    the descriptive Background/Tone fields the Train wizard writes."""
    def field(key: str) -> str:
        value = config.get(key)
        return str(value).strip() if value is not None else ""

    name, title, expertise = field("full_name"), field("title"), field("expertise")
    tone, about = field("tone"), field("about")
    behavior = synthesize_behavior(config)

    if not any([name, title, expertise, about, tone, behavior]):
        return None

    parts: list[str] = []
    who = ", ".join(p for p in (name, title) if p)
    parts.append(f"You are {who}." if who else "You are a helpful AI assistant.")
    if expertise:
        parts.append(f"Your expertise is {expertise}.")
    if about:
        parts.append(about if about.endswith((".", "!", "?")) else about + ".")
    if tone:
        parts.append(f"Write in a {tone} tone.")
    # Keep the grounding rule the default identity carried, so persona workers stay evidence-bound.
    if behavior:
        return f'{" ".join(parts)}\n\n{behavior}\n\n{GROUNDING_INSTRUCTION}'
    parts.append(GROUNDING_INSTRUCTION)
    return " ".join(parts)
