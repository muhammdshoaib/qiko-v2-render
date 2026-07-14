"""Domain dataclass + store protocol for generic in-app notifications.

Mirrors app.modules.crm.service (dataclass + Protocol + in-memory default store, swappable for a
Postgres-backed store behind the same protocol -- see app/db/stores.py). Field names map onto the
`notifications` table (app/db/models.py Notification) and the qiko-backend origin/idg-sales
Notification model (notify_type -> category, type, title, body, metadata, read_at)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

# Notification categories name the source module (generic/reusable -- Pre-Sales will add its own).
CATEGORY_SALES_INTELLIGENCE = "sales_intelligence"
CATEGORY_GENERAL = "general"

# Sales-Intelligence event types (the 5 triggers from the non-AI components matrix + reviewer-assigned).
TYPE_REVIEW_REQUIRED = "review_required"
TYPE_SF_SYNC_SUCCESS = "sf_sync_success"
TYPE_SF_SYNC_FAILED = "sf_sync_failed"
TYPE_SCAN_FAILED = "scan_failed"
TYPE_DEADLINE_REMINDER = "deadline_reminder"
TYPE_REVIEWER_ASSIGNED = "reviewer_assigned"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Notification:
    id: str
    tenant: str
    type: str
    title: str
    body: str = ""
    category: str = CATEGORY_GENERAL
    user_id: str | None = None  # None == tenant-wide (every user in the tenant sees it)
    agent_id: str | None = None
    opportunity_id: str | None = None
    metadata: dict = field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)

    def is_read(self) -> bool:
        return self.read_at is not None


class NotificationStore(Protocol):
    async def add(self, notification: Notification) -> Notification: ...
    async def get(self, tenant: str, notification_id: str) -> Notification | None: ...
    async def list_for_user(self, tenant: str, user_id: str | None, *, category: str | None = None,
                            unread_only: bool = False, limit: int | None = None) -> list[Notification]: ...
    async def mark_read(self, tenant: str, notification_id: str, user_id: str | None) -> Notification | None: ...
    async def mark_all_read(self, tenant: str, user_id: str | None, *, category: str | None = None) -> int: ...
    async def unread_count(self, tenant: str, user_id: str | None, *, category: str | None = None) -> int: ...


def _visible_to(n: Notification, user_id: str | None) -> bool:
    """A notification is visible to a caller when it's tenant-wide (user_id is None) or addressed
    to that exact user. Callers only ever pass their own verified user_id (BOLA-safe)."""
    return n.user_id is None or n.user_id == user_id


@dataclass
class InMemoryNotificationStore:
    _by_id: dict[str, Notification] = field(default_factory=dict)

    async def add(self, notification: Notification) -> Notification:
        self._by_id[notification.id] = notification
        return notification

    async def get(self, tenant: str, notification_id: str) -> Notification | None:
        n = self._by_id.get(notification_id)
        return n if n and n.tenant == tenant else None

    async def list_for_user(self, tenant: str, user_id: str | None, *, category: str | None = None,
                            unread_only: bool = False, limit: int | None = None) -> list[Notification]:
        items = [n for n in self._by_id.values()
                 if n.tenant == tenant and _visible_to(n, user_id)
                 and (category is None or n.category == category)
                 and (not unread_only or not n.is_read())]
        items.sort(key=lambda n: n.created_at, reverse=True)
        return items[:limit] if limit else items

    async def mark_read(self, tenant: str, notification_id: str, user_id: str | None) -> Notification | None:
        n = self._by_id.get(notification_id)
        if n is None or n.tenant != tenant or not _visible_to(n, user_id):
            return None
        if n.read_at is None:
            n.read_at = _now()
        return n

    async def mark_all_read(self, tenant: str, user_id: str | None, *, category: str | None = None) -> int:
        count = 0
        for n in self._by_id.values():
            if (n.tenant == tenant and _visible_to(n, user_id) and not n.is_read()
                    and (category is None or n.category == category)):
                n.read_at = _now()
                count += 1
        return count

    async def unread_count(self, tenant: str, user_id: str | None, *, category: str | None = None) -> int:
        return len(await self.list_for_user(tenant, user_id, category=category, unread_only=True))
