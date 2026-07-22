"""Admin-created Stripe payment links with a logged lifecycle + email delivery.

A link is created via Stripe, logged (pending), and emailed to the customer. Webhook status
(paid/void/failed) updates the log by session id; an admin can also force mark-as-paid.
Stripe I/O and email sit behind protocols so the flow is testable without the network.

The link log sits behind a PaymentLinkStore protocol: in-memory by default (dev/tests), swapped
for the Postgres-backed store (app.db.sync_stores.SqlPaymentLinkStore) under USE_DB_STORES so a
link and its paid/void status survive a restart.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.modules.email.sender import EmailSender

_VALID_STATUS = {"pending", "paid", "open", "void", "failed"}


class PaymentLinkGateway(Protocol):
    def create_payment_link(self, *, amount_cents: int, session_id: str, recurring: bool) -> str: ...


@dataclass
class PaymentLinkLog:
    session_id: str
    customer_email: str
    amount_cents: int
    url: str
    status: str = "pending"


class PaymentLinkStore(Protocol):
    """State backend for PaymentLinkService. Both the in-memory store and the Postgres-backed
    SqlPaymentLinkStore implement this synchronous interface."""
    def add(self, log: PaymentLinkLog) -> None: ...
    def get(self, session_id: str) -> PaymentLinkLog | None: ...
    def set_status(self, session_id: str, status: str) -> None: ...
    def list_for_email(self, customer_email: str) -> list[PaymentLinkLog]: ...
    def mark_pending_paid_for_email(self, customer_email: str) -> int: ...


@dataclass
class InMemoryPaymentLinkStore:
    """Process-local payment-link log (dev/tests). Lost on restart."""
    _logs: dict[str, PaymentLinkLog] = field(default_factory=dict)

    def add(self, log: PaymentLinkLog) -> None:
        self._logs[log.session_id] = log

    def get(self, session_id: str) -> PaymentLinkLog | None:
        return self._logs.get(session_id)

    def set_status(self, session_id: str, status: str) -> None:
        self._logs[session_id].status = status  # KeyError if unknown (matches prior behaviour)

    def list_for_email(self, customer_email: str) -> list[PaymentLinkLog]:
        return [x for x in self._logs.values() if x.customer_email == customer_email]

    def mark_pending_paid_for_email(self, customer_email: str) -> int:
        changed = 0
        for log in self._logs.values():
            if log.customer_email == customer_email and log.status == "pending":
                log.status = "paid"
                changed += 1
        return changed


@dataclass
class PaymentLinkService:
    gateway: PaymentLinkGateway
    email: EmailSender
    store: PaymentLinkStore = field(default_factory=InMemoryPaymentLinkStore)

    def create(self, customer_email: str, amount_cents: int, *, recurring: bool = False) -> PaymentLinkLog:
        session_id = uuid.uuid4().hex
        url = self.gateway.create_payment_link(amount_cents=amount_cents, session_id=session_id, recurring=recurring)
        log = PaymentLinkLog(session_id=session_id, customer_email=customer_email,
                             amount_cents=amount_cents, url=url)
        self.store.add(log)
        self.email.send(to=customer_email, subject="Your Qiko payment link",
                        body=f"Complete your payment here:\n\n{url}")
        return log

    def update_status(self, session_id: str, status: str) -> PaymentLinkLog:
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status}")
        self.store.set_status(session_id, status)
        return self.store.get(session_id)

    def mark_as_paid_for_user(self, customer_email: str) -> int:
        """Admin override: flip all of a customer's pending links to paid. Returns count changed."""
        return self.store.mark_pending_paid_for_email(customer_email)

    def logs_for(self, customer_email: str) -> list[PaymentLinkLog]:
        return self.store.list_for_email(customer_email)
