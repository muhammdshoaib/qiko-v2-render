"""Sales-Intelligence notification triggers -- port of
app/Services/IdgSales/IdgSalesNotificationService.php, on top of the generic
app.modules.notifications.NotificationService (in-product inbox only, no FCM push).

Each helper builds the title/body for one event and writes an inbox row via the generic service.
Recipient rule: address the opportunity's assigned reviewer when one is set, otherwise leave
user_id NULL (tenant-wide, so any team member in the tenant sees it) -- the V2 analogue of the
Laravel service's "assigned reviewer else agent owner" fan-out.

Every method swallows its own errors (best-effort, mirroring the source's try/report) so a
notification failure never breaks the scan/push/review flow that triggered it."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.modules.notifications.models import (
    CATEGORY_SALES_INTELLIGENCE,
    TYPE_DEADLINE_REMINDER,
    TYPE_REVIEW_REQUIRED,
    TYPE_REVIEWER_ASSIGNED,
    TYPE_SCAN_FAILED,
    TYPE_SF_SYNC_FAILED,
    TYPE_SF_SYNC_SUCCESS,
)
from app.modules.notifications.service import NotificationService

logger = logging.getLogger(__name__)


@dataclass
class SalesNotificationService:
    notifications: NotificationService = field(default_factory=NotificationService)

    async def _safe_notify(self, **kwargs) -> None:
        try:
            await self.notifications.notify(category=CATEGORY_SALES_INTELLIGENCE, **kwargs)
        except Exception:  # best-effort: never break the triggering flow
            logger.exception("sales-intelligence notification failed")

    async def notify_review_required(self, opportunity) -> None:
        """Fires when an opportunity lands in `awaiting_review` (manual create or a scan)."""
        if opportunity.stage != "awaiting_review":
            return
        await self._safe_notify(
            tenant=opportunity.tenant, type=TYPE_REVIEW_REQUIRED, title="Review required",
            body=f"{opportunity.title} is ready for human validation.",
            user_id=opportunity.assigned_reviewer_user_id, agent_id=opportunity.agent_id,
            opportunity_id=opportunity.id,
            metadata={"opportunityTitle": opportunity.title, "stage": opportunity.stage})

    async def notify_reviewer_assigned(self, opportunity, reviewer_user_id: str,
                                       actor_user_id: str | None = None) -> None:
        await self._safe_notify(
            tenant=opportunity.tenant, type=TYPE_REVIEWER_ASSIGNED, title="Reviewer assigned",
            body=f"You were assigned to review: {opportunity.title}",
            user_id=reviewer_user_id, agent_id=opportunity.agent_id, opportunity_id=opportunity.id,
            metadata={"opportunityTitle": opportunity.title, "actorUserId": actor_user_id})

    async def notify_salesforce_sync_success(self, opportunity, salesforce_id: str) -> None:
        await self._safe_notify(
            tenant=opportunity.tenant, type=TYPE_SF_SYNC_SUCCESS, title="Salesforce Sync Successful",
            body=f"{opportunity.title} was created in Salesforce ({salesforce_id}).",
            user_id=opportunity.assigned_reviewer_user_id, agent_id=opportunity.agent_id,
            opportunity_id=opportunity.id,
            metadata={"opportunityTitle": opportunity.title, "salesforceOpportunityId": salesforce_id})

    async def notify_salesforce_sync_failed(self, opportunity, error: str) -> None:
        await self._safe_notify(
            tenant=opportunity.tenant, type=TYPE_SF_SYNC_FAILED, title="Salesforce Sync Failed",
            body=f"{opportunity.title} failed: {error}",
            user_id=opportunity.assigned_reviewer_user_id, agent_id=opportunity.agent_id,
            opportunity_id=opportunity.id,
            metadata={"opportunityTitle": opportunity.title, "error": error})

    async def notify_scan_failed(self, tenant: str, agent_id: str, source_key: str, error: str) -> None:
        await self._safe_notify(
            tenant=tenant, type=TYPE_SCAN_FAILED, title="Scan Failed",
            body=f"{source_key.upper()} scan failed: {error}", agent_id=agent_id,
            metadata={"sourceKey": source_key, "error": error})

    async def notify_deadline_reminder(self, opportunity, due_in_days: int) -> None:
        """Callable by the scheduler later; also usable from a manual "send reminder" action."""
        if due_in_days < 0:
            body = f"{opportunity.title} submission deadline passed {abs(due_in_days)} day(s) ago."
        elif due_in_days == 0:
            body = f"{opportunity.title} submission deadline is today."
        elif due_in_days == 1:
            body = f"{opportunity.title} submission deadline is tomorrow (1 day left)."
        else:
            body = f"{opportunity.title} submission deadline is in {due_in_days} days."
        await self._safe_notify(
            tenant=opportunity.tenant, type=TYPE_DEADLINE_REMINDER, title="Deadline reminder",
            body=body, user_id=opportunity.assigned_reviewer_user_id, agent_id=opportunity.agent_id,
            opportunity_id=opportunity.id,
            metadata={"opportunityTitle": opportunity.title, "dueInDays": due_in_days,
                      "deadlineAt": opportunity.deadline_at.isoformat() if opportunity.deadline_at else None})
