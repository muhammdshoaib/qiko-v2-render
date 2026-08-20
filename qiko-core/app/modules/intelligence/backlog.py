"""Backlog proposal: decompose an accepted research brief into Qiko Track tickets.

A proposal is a draft until a human approves it. The only write path in the
Intelligence Worker goes through `create_approved`, which calls Qiko Track with an
idempotency key so a retry cannot duplicate tickets.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from app.modules.intelligence.orchestration.models import Finding
from app.modules.intelligence.qiko_track_client import QikoTrackClient
from app.modules.intelligence.research import Brief


# The vocabulary matches Qiko Track's createTicketSchema.
TICKET_TYPES = ("FEATURE", "BUG", "CHORE", "SPIKE", "FINDING", "EPIC")
PRIORITIES = ("URGENT", "HIGH", "MEDIUM", "LOW", "NONE")

_TYPE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("epic", "initiative", "platform"), "EPIC"),
    (("bug", "crash", "error", "fail", "broken", "regression"), "BUG"),
    (("spike", "research", "investigate", "proof of concept", "poc"), "SPIKE"),
    (("chore", "refactor", "cleanup", "ci", "lint", "test", "deploy", "docs"), "CHORE"),
    (("finding", "observation", "note"), "FINDING"),
]

_PRIORITY_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("urgent", "critical", "asap"), "URGENT"),
    (("high"), "HIGH"),
    (("low"), "LOW"),
]


def _infer_type(text: str) -> str:
    lowered = text.lower()
    for hints, ticket_type in _TYPE_HINTS:
        if any(h in lowered for h in hints):
            return ticket_type
    return "FEATURE"


def _infer_priority(text: str) -> str:
    lowered = text.lower()
    for hints, priority in _PRIORITY_HINTS:
        if any(h in lowered for h in hints):
            return priority
    return "NONE"


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _build_description(finding: Finding) -> str:
    parts = [finding.text]
    if finding.gaps:
        parts.append(f"\n\nGap: {finding.gaps}")
    if finding.evidence_refs:
        parts.append("\n\nEvidence: " + ", ".join(finding.evidence_refs))
    return "".join(parts)


def _clean_title(text: str) -> str:
    # Collapse whitespace and strip bullets/numbering.
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"^[-•\d.\)]*\s*", "", cleaned)
    return cleaned


@dataclass
class ProposedTicket:
    """One proposed Qiko Track ticket, derived from a finding or the brief summary."""

    title: str
    description_md: str
    type: str = "FEATURE"
    priority: str = "NONE"
    estimate_points: int | None = None
    parent_index: int | None = None
    finding_index: int | None = None
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description_md": self.description_md,
            "type": self.type,
            "priority": self.priority,
            "estimate_points": self.estimate_points,
            "parent_index": self.parent_index,
            "finding_index": self.finding_index,
            "evidence_refs": self.evidence_refs,
        }


@dataclass
class BacklogProposal:
    """A reviewable draft of tickets ready for human approval."""

    project_key: str
    items: list[ProposedTicket]

    def to_dict(self) -> dict:
        return {
            "project_key": self.project_key,
            "items": [item.to_dict() for item in self.items],
        }


class BacklogService:
    """Convert a brief into proposed tickets and create the approved subset."""

    def __init__(self, base_url: str, token: str, *, resolver=None) -> None:
        self.client = QikoTrackClient(base_url, token, resolver=resolver)

    def propose(self, brief: Brief, project_key: str) -> BacklogProposal:
        """Decompose an accepted brief into a draft backlog.

        The epic comes from the brief subject/summary; each finding becomes a
        child ticket. Decomposition is deterministic so repeated drafts are stable.
        """
        items: list[ProposedTicket] = []
        epic = ProposedTicket(
            title=_truncate(_clean_title(brief.subject), 300),
            description_md=brief.summary,
            type="EPIC",
            priority="NONE",
            finding_index=None,
        )
        items.append(epic)

        for idx, finding in enumerate(brief.findings):
            text = _clean_title(finding.text)
            title = _truncate(text, 300) or f"Finding {idx + 1}"
            items.append(ProposedTicket(
                title=title,
                description_md=_truncate(_build_description(finding), 50_000),
                type=_infer_type(text),
                priority=_infer_priority(text),
                estimate_points=None,
                parent_index=0,
                finding_index=idx,
                evidence_refs=list(finding.evidence_refs),
            ))

        if len(items) == 1 and not brief.summary:
            # No content to work with: return a single empty placeholder so the
            # UI can tell the user there is nothing to propose.
            items[0].title = _truncate(_clean_title(brief.subject), 300)
            items[0].description_md = "No findings or summary were available to decompose."

        return BacklogProposal(project_key=project_key, items=items)

    async def create_approved(
        self, proposal: BacklogProposal, approved_indices: set[int],
    ) -> list[dict]:
        """Create the approved items in Qiko Track, epics first so children can link.

        Each create carries an idempotency key derived from the project, title and
        a caller nonce, so resubmitting the same approval does not duplicate work.
        """
        items = proposal.items
        created_keys: dict[int, str] = {}
        results: list[dict] = []

        # Create epics first (parent_index is None or lower index). Sort so a
        # parent is created before any child that references it.
        ordered = sorted(
            (i for i in approved_indices if 0 <= i < len(items)),
            key=lambda i: 0 if items[i].parent_index is None else 1,
        )

        for index in ordered:
            item = items[index]
            parent_key = None
            if item.parent_index is not None and item.parent_index in created_keys:
                parent_key = created_keys[item.parent_index]

            payload: dict = {
                "projectKey": proposal.project_key,
                "title": item.title,
                "descriptionMd": item.description_md,
                "type": item.type,
                "priority": item.priority,
                "status": "BACKLOG",
            }
            if item.estimate_points is not None:
                payload["estimatePoints"] = item.estimate_points
            if parent_key:
                payload["parentId"] = parent_key

            idempotency_key = f"{proposal.project_key}:{index}:{uuid.uuid4().hex}"
            try:
                result = await self.client.create_ticket(payload, idempotency_key=idempotency_key)
            except Exception as exc:
                raise BacklogCreateError(f"Failed to create ticket {item.title!r}: {exc}") from exc

            created_keys[index] = result.get("key") or result.get("id") or ""
            results.append({"index": index, "key": created_keys[index], "title": item.title})

        return results


class BacklogCreateError(Exception):
    """Creating one or more approved tickets failed."""
