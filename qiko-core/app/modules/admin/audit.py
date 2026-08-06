"""Recording platform-admin actions that the two existing audit tables do not cover.

Deliberately fire-and-forget from the caller's point of view: a mutation that succeeded must not be
reported as failed because the audit write failed. That is the opposite of the usual advice, and it is
the right trade here because these endpoints already return the mutated state to the caller and the
mutation itself is committed. Losing an audit row is bad; telling an operator their change failed when
it did not, and having them repeat it, is worse.

The failure is logged loudly so a persistently broken audit path is visible rather than silent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

logger = logging.getLogger(__name__)

# The actions this table records. A closed set rather than a free string, so a typo becomes a failing
# test rather than an audit row nobody can find later.
STUDIO_TOGGLED = "studio_toggled"
CUSTOMER_SOFT_DELETED = "customer_soft_deleted"
COST_CAP_SET = "cost_cap_set"
COST_CAP_REMOVED = "cost_cap_removed"
TENANT_ROLE_CHANGED = "tenant_role_changed"
WORKER_STATUS_CHANGED = "worker_status_changed"

ACTIONS = frozenset({
    STUDIO_TOGGLED, CUSTOMER_SOFT_DELETED, COST_CAP_SET, COST_CAP_REMOVED,
    TENANT_ROLE_CHANGED, WORKER_STATUS_CHANGED,
})


@dataclass(frozen=True)
class AdminAction:
    action: str
    target_type: str
    target_id: str
    actor_email: str
    tenant_id: str | None = None
    before: str | None = None
    after: str | None = None
    reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AdminAuditStore(Protocol):
    async def add(self, entry: AdminAction) -> None: ...
    async def list(self, *, action: str | None = None, tenant_id: str | None = None,
                   target_id: str | None = None, limit: int = 100) -> list[AdminAction]: ...


@dataclass
class InMemoryAdminAuditStore:
    entries: list[AdminAction] = field(default_factory=list)

    async def add(self, entry: AdminAction) -> None:
        self.entries.append(entry)

    async def list(self, *, action=None, tenant_id=None, target_id=None, limit=100) -> list[AdminAction]:
        rows = [
            entry for entry in self.entries
            if (action is None or entry.action == action)
            and (tenant_id is None or entry.tenant_id == tenant_id)
            and (target_id is None or entry.target_id == target_id)
        ]
        rows.sort(key=lambda entry: entry.created_at, reverse=True)
        return rows[:limit]


async def record(store, entry: AdminAction) -> None:
    """Write an audit row, never raising. See the module docstring for why."""
    if store is None:
        return
    if entry.action not in ACTIONS:
        # A programming error, not an operator error, so it is loud but still not fatal.
        logger.error("unknown admin audit action", extra={"source": "admin.audit",
                                                          "action": entry.action})
    try:
        await store.add(entry)
    except Exception as error:  # noqa: BLE001 - see module docstring
        logger.error("admin audit write failed", extra={
            "source": "admin.audit", "action": entry.action, "target": entry.target_id,
            "actor": entry.actor_email, "error": str(error)})


def entry_json(entry: AdminAction) -> dict:
    return {"action": entry.action, "target_type": entry.target_type, "target_id": entry.target_id,
            "tenant_id": entry.tenant_id, "actor_email": entry.actor_email,
            "before": entry.before, "after": entry.after, "reason": entry.reason,
            "created_at": entry.created_at.isoformat()}
