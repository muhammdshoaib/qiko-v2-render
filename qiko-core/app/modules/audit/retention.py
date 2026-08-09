"""Retention and erasure for the audit trail.

The trail accumulates emails, IP addresses and user agents, and until now it had no expiry, no
pseudonymisation and no erasure path, while `AuditEventRow`'s own docstring claimed the source address
was nulled after six months. That claim is what this module makes true.

TWO TIERS, AND WHY THESE PERIODS.

Events are kept for 13 months. That covers an annual SOC 2 Type II observation window plus a buffer for
the sample requests that arrive after it closes, and it sits above the 12-month floor that PCI DSS
10.5.1 states and inside the band CNIL treats as justifiable for access traceability. Nothing in SOC 2
or ISO 27001 names a number; what they require is that the stated policy and the implemented one match,
which is the actual reason this is code and not a paragraph.

Network identifiers are kept for 6 months, then nulled in place while the event itself survives. That is
CNIL's baseline for traceability logs and it is the cheapest possible answer to a minimisation
challenge: it costs a field, not an event, so the completeness the audit relies on is untouched.

Seven years was considered and rejected for the hot tier. Seven years of raw personal identifiers in a
queryable table is precisely what a data protection review challenges, and it buys nothing an auditor
asks for. The long archive is a separate concern and is pseudonymised on export.

ERASURE PSEUDONYMISES, IT NEVER DELETES A ROW.

A gap in an audit trail is indistinguishable from tampering, and deleting rows to satisfy an erasure
request destroys the completeness property the whole table exists for. So identifiers are replaced with
a keyed HMAC and everything else, the timestamps, the action, the outcome, the diffs, stays exactly as
it was.

The circularity that catches most implementations is that the erasure event itself must not re-create
the identifier it just erased. So `privacy.subject_erased` records a pseudonym, a request reference and
a row count, never the address. The mapping from that reference back to a person lives in the DSAR
ticket under its own retention, which is where a regulator expects to find it.

Platform-admin actor identities are deliberately NOT pseudonymised on request while the records are
within the retention window. Staff have erasure rights, but Article 17(3) applies more strongly to
employment-related security records, and an audit trail with no readable actor fails the control it
exists to evidence. That asymmetry is a decision, so it is written here rather than made per request.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Kept deliberately as named constants rather than settings: a retention period that can be changed by
# an environment variable is a retention period that will silently differ between environments, and the
# number in the policy has to be the number in the code.
EVENT_RETENTION_DAYS = 396  # 13 months
NETWORK_RETENTION_DAYS = 183  # 6 months

# Deletes run in bounded batches. A single unbounded DELETE over a large table takes a long lock and
# can time out halfway, leaving an unpredictable amount done.
DELETE_BATCH = 5_000


@dataclass(frozen=True)
class RetentionResult:
    events_deleted: int
    addresses_cleared: int
    cutoff_events: datetime
    cutoff_network: datetime

    def as_metadata(self) -> dict:
        return {"events_deleted": self.events_deleted,
                "addresses_cleared": self.addresses_cleared,
                "cutoff_events": self.cutoff_events.isoformat(),
                "cutoff_network": self.cutoff_network.isoformat()}


def cutoffs(now: datetime | None = None) -> tuple[datetime, datetime]:
    reference = now or datetime.now(timezone.utc)
    return (reference - timedelta(days=EVENT_RETENTION_DAYS),
            reference - timedelta(days=NETWORK_RETENTION_DAYS))


def audit_subject_pseudonym(identifier: str) -> str:
    """A one-way, keyed pseudonym for an audit subject.

    Reuses the consent module's versioned keyring rather than introducing a second scheme, which gives
    two things for free: rotation without breaking existing lookups, and crypto-shredding as a genuine
    hard-delete lever if a regulator ever demands one, since destroying a key version makes every
    pseudonym under it unlinkable.

    The namespace differs from consent's, so a subject's audit pseudonym and consent pseudonym cannot be
    correlated by anyone holding only one of the two tables.
    """
    from app.modules.consent.service import pseudonymous_subject

    return pseudonymous_subject("audit-subject", identifier.strip().lower())[:64]
