"""The daily off-database copy of the audit trail, with a tamper-evidence digest.

WHY THIS AND NOT HASH CHAINING.

The question a tender asks behind the word "immutable" reduces to two properties: the application cannot
alter historic rows, and a second copy exists that the people who administer the primary database cannot
alter either. A per-row `prev_hash` chain answers neither on its own, because the head of the chain lives
in the same database as the rows, so anyone who can rewrite a row can rewrite the chain. It also forces
serialised inserts, breaks under partitioning, and makes the erasure-pseudonymisation UPDATE either
impossible or a chain-rebuild exercise.

A daily export to write-once storage answers both, plus the long-retention question and the
pseudonymisation boundary, for a fraction of the cost. The digest is what makes it tamper-EVIDENT rather
than merely redundant: any later alteration to a row inside a covered day changes that day's digest, and
the digest is held outside the database in storage that cannot be overwritten.

WHAT THE DIGEST COVERS, AND WHAT IT DOES NOT.

It covers the rows as exported, in a fixed order, over the fields that are meant to be immutable. It
deliberately EXCLUDES the pseudonymisation columns, because an erasure request legitimately rewrites
identifiers in place and must not be indistinguishable from tampering. That is a real trade: an attacker
who rewrites an identifier through the erasure path leaves the digest intact. The compensating control is
that erasure is itself audited, gated on manage_admins, and records the row count it touched.

Saying that out loud matters more than the digest itself. A tamper-evidence claim that does not state its
own boundary is worse than no claim.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

logger = logging.getLogger(__name__)

# The fields the digest is computed over. Explicit rather than "everything", so adding a column cannot
# silently change every historic digest and make old exports unverifiable.
DIGESTED_FIELDS = (
    "event_id", "action", "category", "outcome", "occurred_at", "actor_type", "actor_id",
    "target_type", "target_id", "tenant_id", "request_id", "service", "environment",
)

# Excluded on purpose. See the module docstring: erasure rewrites these, and it must not look like
# tampering.
EXCLUDED_FROM_DIGEST = ("subject_pseudonym", "pseudonymised_at", "actor_label", "target_label",
                        "source_ip", "user_agent")


@dataclass(frozen=True)
class DayExport:
    day: date
    row_count: int
    digest: str
    previous_digest: str | None
    first_event_id: str | None
    last_event_id: str | None
    body: bytes

    @property
    def key(self) -> str:
        # Partitioned by day so a retrieval for a date range is a prefix listing rather than a scan, and
        # so an Object Lock retention period applies per object rather than to one growing blob.
        return f"audit/{self.day:%Y/%m}/{self.day:%Y-%m-%d}.ndjson"

    def manifest(self) -> dict:
        return {"day": self.day.isoformat(), "row_count": self.row_count, "digest": self.digest,
                "previous_digest": self.previous_digest, "first_event_id": self.first_event_id,
                "last_event_id": self.last_event_id, "digested_fields": list(DIGESTED_FIELDS)}


def _canonical(row: dict) -> str:
    """One row, reduced to the fields under the digest, in a fixed order.

    Serialised with sorted keys and no whitespace so the same row always produces the same bytes
    regardless of how the dict was built or which driver returned it.
    """
    subset = {field: row.get(field) for field in DIGESTED_FIELDS}
    return json.dumps(subset, sort_keys=True, separators=(",", ":"), default=str)


def build_day_export(rows: list[dict], day: date, previous_digest: str | None = None) -> DayExport:
    """Turn one day's rows into the object to store, plus its digest.

    Rows are sorted by (occurred_at, event_id) rather than by primary key. The key is assigned at insert
    and occurred_at is set when the event happened, so the two can disagree, and a digest computed in key
    order would differ between an export and a re-export of the same day after a late-arriving row.
    """
    ordered = sorted(rows, key=lambda row: (str(row.get("occurred_at") or ""),
                                            str(row.get("event_id") or "")))
    lines = [json.dumps(row, sort_keys=True, default=str) for row in ordered]
    body = ("\n".join(lines) + ("\n" if lines else "")).encode()

    running = hashlib.sha256()
    # Chained to the previous day, so a missing day is detectable as well as a modified one. Deleting a
    # whole object is the easier attack, and a per-day digest with no link would not notice.
    running.update((previous_digest or "").encode())
    for row in ordered:
        running.update(_canonical(row).encode())
        running.update(b"\n")

    return DayExport(
        day=day, row_count=len(ordered), digest=running.hexdigest(), previous_digest=previous_digest,
        first_event_id=ordered[0].get("event_id") if ordered else None,
        last_event_id=ordered[-1].get("event_id") if ordered else None,
        body=body)


def verify(export: DayExport, rows: list[dict]) -> bool:
    """Recompute the digest from rows and compare. This is the whole point of storing it."""
    return build_day_export(rows, export.day, export.previous_digest).digest == export.digest


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC bounds for a day. Half-open, so a row at exactly midnight belongs to one day only."""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)
