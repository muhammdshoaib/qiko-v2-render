"""Stripe webhook: signature verification (Stripe's own t=/v1= scheme, not the generic HMAC) +
idempotent invoice sync. Duplicate deliveries (same event id) are ignored via the shared
IdempotencyGuard; invoices upsert by stripe_invoice_id so re-delivery never double-counts.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.modules.billing.payment_links import PaymentLinkService
from app.modules.billing.subscriptions import Subscription, SubscriptionService
from app.modules.channels.webhooks import IdempotencyGuard


class IdempotencyStore(Protocol):
    def is_duplicate(self, event_id: str) -> bool: ...


def _parse_sig_header(header: str) -> tuple[str, str]:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    return parts.get("t", ""), parts.get("v1", "")


WEBHOOK_TOLERANCE_SECONDS = 300


def verify_stripe_signature(secret: str, payload: bytes, sig_header: str) -> bool:
    t, v1 = _parse_sig_header(sig_header)
    if not secret or not t or not v1:
        return False
    try:
        ts = int(t)
    except ValueError:
        return False
    now = datetime.now(timezone.utc).timestamp()
    if abs(now - ts) > WEBHOOK_TOLERANCE_SECONDS:
        return False
    signed = f"{t}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


@dataclass
class Invoice:
    stripe_invoice_id: str
    customer_id: str
    amount_cents: int
    status: str
    currency: str | None = None
    number: str | None = None
    hosted_invoice_url: str | None = None
    invoice_pdf: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None

    @classmethod
    def from_stripe_object(cls, obj: dict) -> "Invoice":
        """Build an Invoice from a Stripe invoice object (webhook payload or list API row)."""
        def _ts(name: str) -> datetime | None:
            ts = obj.get(name)
            return datetime.fromtimestamp(int(ts), tz=timezone.utc) if ts else None
        amount = (obj.get("amount_paid") if obj.get("status") == "paid"
                  else obj.get("amount_due")) or 0
        return cls(
            stripe_invoice_id=obj.get("id", ""),
            customer_id=obj.get("customer") or "",
            amount_cents=int(amount or 0),
            status=obj.get("status", "open"),
            currency=obj.get("currency"),
            number=obj.get("number"),
            hosted_invoice_url=obj.get("hosted_invoice_url"),
            invoice_pdf=obj.get("invoice_pdf"),
            period_start=_ts("period_start"),
            period_end=_ts("period_end"))


@dataclass
class InvoiceStore:
    _by_id: dict[str, Invoice] = field(default_factory=dict)

    def upsert(self, inv: Invoice) -> bool:
        """Idempotent by stripe_invoice_id. Returns True if newly inserted, False if updated."""
        is_new = inv.stripe_invoice_id not in self._by_id
        self._by_id[inv.stripe_invoice_id] = inv
        return is_new

    def get(self, invoice_id: str) -> Invoice | None:
        return self._by_id.get(invoice_id)

    def count(self) -> int:
        return len(self._by_id)

    def list(self, customer_id: str | None = None) -> list["Invoice"]:
        return [i for i in self._by_id.values() if customer_id is None or i.customer_id == customer_id]


@dataclass
class StripeWebhookHandler:
    invoices: InvoiceStore = field(default_factory=InvoiceStore)
    idempotency: IdempotencyStore = field(default_factory=IdempotencyGuard)
    # Optional so the handler stays usable/testable standalone; wired in app.main so the webhook
    # can link tenant<->Stripe-customer and activate the subscription on checkout completion.
    subscriptions: "SubscriptionService | None" = None
    payment_links: "PaymentLinkService | None" = None

    def _subscription_from_event(self, obj: dict) -> "Subscription | None":
        """Build a Subscription object from a Stripe subscription object, or None if unparseable."""
        stripe_customer_id = obj.get("customer") or ""
        if self.subscriptions is None or not stripe_customer_id:
            return None
        tenant = self.subscriptions.store.get_tenant_by_customer(stripe_customer_id)
        if not tenant:
            return None
        period_end = None
        ts = obj.get("current_period_end")
        if ts:
            period_end = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        plan = (obj.get("metadata") or {}).get("plan")
        existing = self.subscriptions.status(tenant)
        if plan is None and existing is not None:
            plan = existing.plan
        if plan is None:
            plan = "pro"
        return Subscription(
            customer_id=tenant,
            plan=plan,
            status=obj.get("status", "active"),
            cancel_at_period_end=bool(obj.get("cancel_at_period_end", False)),
            stripe_subscription_id=obj.get("id"),
            current_period_end=period_end,
        )

    def handle(self, event: dict) -> str:
        """Process a (already signature-verified) event; returns the action taken."""
        event_id = event.get("id", "")
        if event_id and self.idempotency.is_duplicate(event_id):
            return "duplicate"
        etype = event.get("type", "")
        obj = event.get("data", {}).get("object", {})
        if etype.startswith("invoice."):
            self.invoices.upsert(Invoice.from_stripe_object(obj))
            return "invoice_synced"
        if etype == "checkout.session.completed":
            # Payment-link checkouts carry the Qiko session id in metadata so we can flip the link
            # to paid even when there is no client_reference_id (subscription checkouts set that).
            qiko_session_id = (obj.get("metadata") or {}).get("qiko_session_id") or ""
            if qiko_session_id and self.payment_links is not None:
                log = self.payment_links.store.get(qiko_session_id)
                if log is not None:
                    self.payment_links.update_status(qiko_session_id, "paid")
                    return "payment_link_paid"
                return "payment_link_unknown"
            # We set client_reference_id=tenant when creating the checkout session
            # (subscriptions.start_checkout), so Stripe echoes it back here. That -- never client
            # input -- is the tenant the new Stripe customer belongs to. Stay defensive: any
            # missing field is a no-op rather than a crash (a webhook must not 500 on odd shapes).
            tenant = obj.get("client_reference_id") or ""
            stripe_customer_id = obj.get("customer") or ""
            if self.subscriptions is not None and tenant and stripe_customer_id:
                # Plan carried on session metadata if the checkout set it; else a sensible default.
                plan = (obj.get("metadata") or {}).get("plan") or "pro"
                self.subscriptions.link_customer(tenant, stripe_customer_id)
                self.subscriptions.activate(tenant, plan)
                return "subscription_activated"
            return "checkout_completed"
        if etype in ("customer.subscription.created", "customer.subscription.updated"):
            sub = self._subscription_from_event(obj)
            if sub is not None:
                self.subscriptions.store.put(sub)
                return "subscription_synced"
            return "ignored"
        if etype == "customer.subscription.deleted":
            sub = self._subscription_from_event(obj)
            if sub is not None:
                sub.status = "canceled"
                self.subscriptions.store.put(sub)
                return "subscription_deleted"
            return "ignored"
        return "ignored"
