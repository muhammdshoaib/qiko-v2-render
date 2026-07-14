"""Generic notification service -- persists in-app inbox rows (no email/FCM push; in-product
first, per the Queries sheet). Port of app/Services/Notifications/NotificationService.php's
`notify()` inbox side, minus the Firebase Cloud Messaging fan-out.

Verticals depend only on the NotificationStore protocol, so the same service backs both the
in-memory dev default and the Postgres-backed SqlNotificationStore (app/db/stores.py)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.modules.notifications.models import (
    CATEGORY_GENERAL,
    InMemoryNotificationStore,
    Notification,
    NotificationStore,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class NotificationService:
    store: NotificationStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryNotificationStore()

    async def notify(self, tenant: str, type: str, title: str, body: str = "", *,
                     category: str = CATEGORY_GENERAL, user_id: str | None = None,
                     agent_id: str | None = None, opportunity_id: str | None = None,
                     metadata: dict | None = None) -> Notification:
        return await self.store.add(Notification(
            id=_new_id(), tenant=tenant, type=type, title=title, body=body, category=category,
            user_id=user_id, agent_id=agent_id, opportunity_id=opportunity_id, metadata=metadata or {}))

    async def list(self, tenant: str, user_id: str | None, *, category: str | None = None,
                   unread_only: bool = False, limit: int | None = None) -> list[Notification]:
        return await self.store.list_for_user(tenant, user_id, category=category,
                                              unread_only=unread_only, limit=limit)

    async def mark_read(self, tenant: str, notification_id: str, user_id: str | None) -> Notification | None:
        return await self.store.mark_read(tenant, notification_id, user_id)

    async def mark_all_read(self, tenant: str, user_id: str | None, *, category: str | None = None) -> int:
        return await self.store.mark_all_read(tenant, user_id, category=category)

    async def unread_count(self, tenant: str, user_id: str | None, *, category: str | None = None) -> int:
        return await self.store.unread_count(tenant, user_id, category=category)
