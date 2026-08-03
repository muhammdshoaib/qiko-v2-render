"""Synthesize a per-worker persona (identity) prompt from the Train wizard's config.

QIK-315: every worker used to fall back to the generic bid-response-writer voice because the wizard
writes expertise/tone/rules to config but never a `system_prompt`. We build the identity here from
those fields so each worker sounds like itself. This is ONLY the identity -- the generator always
appends the shared output contract (JSON shape), so structured answering is never lost.
"""
from __future__ import annotations


def synthesize_persona(config: dict) -> str | None:
    """Return an identity prompt built from the worker's config, or None when there is no meaningful
    identity config (so the worker keeps the default identity). Never includes secrets: it only reads
    the descriptive Background/Tone fields the Train wizard writes."""
    def field(key: str) -> str:
        value = config.get(key)
        return str(value).strip() if value is not None else ""

    name, title, expertise = field("full_name"), field("title"), field("expertise")
    tone, about = field("tone"), field("about")
    rules, guardrails = field("rules"), field("guardrails")

    if not any([name, title, expertise, about, tone, rules, guardrails]):
        return None

    parts: list[str] = []
    if name or title:
        who = "You are " + name + (f", {title}" if title else "")
        parts.append(who.rstrip(", ") + ".")
    else:
        parts.append("You are a helpful AI assistant.")
    if expertise:
        parts.append(f"Your expertise is {expertise}.")
    if about:
        parts.append(about if about.endswith((".", "!", "?")) else about + ".")
    if tone:
        parts.append(f"Write in a {tone} tone.")
    if rules:
        parts.append(f"Always follow these rules: {rules}")
    if guardrails:
        parts.append(f"Never violate these guardrails: {guardrails}")
    # Keep the grounding rule the default identity carried, so persona workers stay evidence-bound.
    parts.append("Answer using ONLY the supplied evidence; do not invent facts, dates, names, or "
                 "figures. If the evidence is insufficient, say so.")
    return " ".join(parts)
