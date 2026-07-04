"""Stripe webhook: signature verification (Stripe's own t=/v1= scheme, not the generic HMAC) +
idempotent invoice sync. Duplicate deliveries (same event id) are ignored via the shared
IdempotencyGuard; invoices upsert by stripe_invoice_id so re-delivery never double-counts.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from app.modules.channels.webhooks import IdempotencyGuard


def _parse_sig_header(header: str) -> tuple[str, str]:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    return parts.get("t", ""), parts.get("v1", "")


def verify_stripe_signature(secret: str, payload: bytes, sig_header: str) -> bool:
    t, v1 = _parse_sig_header(sig_header)
    if not secret or not t or not v1:
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
    idempotency: IdempotencyGuard = field(default_factory=IdempotencyGuard)

    def handle(self, event: dict) -> str:
        """Process a (already signature-verified) event; returns the action taken."""
        event_id = event.get("id", "")
        if event_id and self.idempotency.is_duplicate(event_id):
            return "duplicate"
        etype = event.get("type", "")
        obj = event.get("data", {}).get("object", {})
        if etype.startswith("invoice."):
            self.invoices.upsert(Invoice(
                stripe_invoice_id=obj.get("id", ""),
                customer_id=obj.get("customer", ""),
                amount_cents=int(obj.get("amount_paid", obj.get("amount_due", 0)) or 0),
                status=obj.get("status", "open")))
            return "invoice_synced"
        if etype == "checkout.session.completed":
            return "checkout_completed"
        return "ignored"
