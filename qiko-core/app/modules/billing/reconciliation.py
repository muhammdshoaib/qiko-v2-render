"""Scheduled/manual reconciliation of Stripe invoices into the platform invoice store.

Keeps `billing_invoices` in sync with Stripe for open invoices that have been paid/voided and for
new invoices created outside webhooks. The service is store-agnostic and gateway-agnostic; the arq
worker builds it from the worker-side sessionmaker, and the API builds it from `app.state`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.modules.billing.webhook import Invoice

logger = logging.getLogger(__name__)


class InvoiceStoreProtocol(Protocol):
    def upsert(self, inv: Invoice) -> bool: ...


class StripeInvoiceGateway(Protocol):
    def list_invoices(self, *, status: str | None = None,
                      created_after: datetime | None = None) -> list[dict]: ...


@dataclass
class InvoiceReconciliationService:
    invoices: InvoiceStoreProtocol
    gateway: StripeInvoiceGateway

    def reconcile(self, *, now: datetime | None = None) -> dict:
        """Pull open invoices plus recently created invoices from Stripe and upsert them.

        Open invoices are refreshed regardless of age so status changes (paid/void) are caught.
        Recently created invoices are pulled to catch anything that arrived between webhook deliveries.
        """
        now = now or datetime.now(timezone.utc)
        created_after = now - timedelta(days=1)
        counts = {"open": 0, "recent": 0}

        for status in ("open", None):
            created = None if status == "open" else created_after
            label = "open" if status == "open" else "recent"
            try:
                rows = self.gateway.list_invoices(status=status, created_after=created)
            except Exception:
                logger.exception("invoice reconciliation failed for status=%s", status or "recent")
                raise
            for row in rows:
                try:
                    inv = Invoice.from_stripe_object(row)
                except (ValueError, TypeError):
                    logger.warning("skipping unparseable Stripe invoice row: %s", row.get("id"))
                    continue
                if not inv.stripe_invoice_id or not inv.customer_id:
                    logger.warning("skipping Stripe invoice row with missing id/customer: %s", row.get("id"))
                    continue
                self.invoices.upsert(inv)
                counts[label] += 1

        logger.info("invoice reconciliation complete", extra=counts)
        return counts
