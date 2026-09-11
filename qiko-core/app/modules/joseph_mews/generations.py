"""Storage for Joseph Mews AI generations, keyed by the caller's requestId.

Three things depend on a generation outliving the process that made it, and none of them worked
while this was three in-memory dicts:

  * **Idempotency.** A client retry after a timeout must return the same result, not draft a
    second, different one. Across a deploy it drafted again.
  * **Outcome reporting.** `POST /insights/{requestId}/outcome` looks the requestId up before
    accepting a report. Anything generated before the last release 404s, so the quality numbers
    reset to zero on every deploy and nobody noticed because they only ever go up.
  * **Reading an insight back.** The app had no way to fetch a generated insight at all; the only
    route was re-POSTing the same requestId and hoping the process had not restarted.

`get()` returns `(seen, result)`. `seen` distinguishes "never asked" from "asked and the
generation failed", which the router needs: the first drafts, the second returns
GENERATION_FAILED. Collapsing them would retry a failing generation forever.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class GenerationKind(StrEnum):
    signal = "signal"
    property_insight = "property_insight"
    portfolio_insight = "portfolio_insight"


@dataclass(frozen=True)
class GenerationOutcomeCounts:
    accurate: int = 0
    inaccurate: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"accurate": self.accurate, "inaccurate": self.inaccurate}


@dataclass
class _Row:
    kind: GenerationKind
    result: dict | None
    investor_ref: str | None = None
    property_name: str | None = None
    location: str | None = None
    postcode: str | None = None
    outcome: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class InMemoryGenerationStore:
    """Dev and test default. Deliberately the same interface as the SQL store so a test exercises
    the router's real code path, and so wiring the wrong one is a one-line difference rather than
    a behavioural surprise (which is exactly how the activity store regressed)."""

    _rows: dict[str, _Row] = field(default_factory=dict)

    async def get(self, tenant: str, request_id: str) -> tuple[bool, dict | None]:
        row = self._rows.get(self._key(tenant, request_id))
        if row is None:
            return False, None
        return True, row.result

    async def put(self, tenant: str, request_id: str, kind: GenerationKind, result: dict | None, *,
                  investor_ref: str | None = None, property_name: str | None = None,
                  location: str | None = None, postcode: str | None = None) -> None:
        self._rows[self._key(tenant, request_id)] = _Row(
            kind=kind, result=result, investor_ref=investor_ref, property_name=property_name,
            location=location, postcode=postcode,
        )

    async def record_outcome(self, tenant: str, request_id: str, outcome: str, note: str) -> bool:
        row = self._rows.get(self._key(tenant, request_id))
        if row is None:
            return False
        row.outcome = outcome
        return True

    async def counts(self, tenant: str, kind: GenerationKind) -> GenerationOutcomeCounts:
        rows = [r for k, r in self._rows.items()
                if k.startswith(f"{tenant}:") and r.kind == kind and r.outcome]
        return GenerationOutcomeCounts(
            accurate=sum(1 for r in rows if r.outcome == "accurate"),
            inaccurate=sum(1 for r in rows if r.outcome == "inaccurate"),
        )

    async def latest_property_insight(self, tenant: str, investor_ref: str, *,
                                      property_name: str | None = None) -> dict | None:
        """Newest successful property insight for one investor, optionally narrowed to one named
        property. Failed generations (`result` None) are skipped: the app asking "what insight do
        you have" wants an insight or nothing, not an error from last week."""
        candidates = [
            r for k, r in self._rows.items()
            if k.startswith(f"{tenant}:")
            and r.kind == GenerationKind.property_insight
            and r.investor_ref == investor_ref
            and r.result is not None
            and (property_name is None or r.property_name == property_name)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.created_at).result

    async def latest_portfolio_insight(self, tenant: str, investor_ref: str) -> dict | None:
        """Newest successful portfolio insight for one investor (JM2-1133), same skip-failures
        rule as latest_property_insight above."""
        candidates = [
            r for k, r in self._rows.items()
            if k.startswith(f"{tenant}:")
            and r.kind == GenerationKind.portfolio_insight
            and r.investor_ref == investor_ref
            and r.result is not None
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.created_at).result

    @staticmethod
    def _key(tenant: str, request_id: str) -> str:
        # Tenant-prefixed so one tenant can never read or overwrite another's generation by
        # guessing a requestId. The SQL store gets the same isolation from its WHERE clause.
        return f"{tenant}:{request_id}"
