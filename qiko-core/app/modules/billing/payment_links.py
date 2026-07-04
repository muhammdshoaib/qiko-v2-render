"""Admin-created Stripe payment links with a logged lifecycle + email delivery.

A link is created via Stripe, logged (pending), and emailed to the customer. Webhook status
(paid/void/failed) updates the log by session id; an admin can also force mark-as-paid.
Stripe I/O and email sit behind protocols so the flow is testable without the network.
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


@dataclass
class PaymentLinkService:
    gateway: PaymentLinkGateway
    email: EmailSender
    _logs: dict[str, PaymentLinkLog] = field(default_factory=dict)

    def create(self, customer_email: str, amount_cents: int, *, recurring: bool = False) -> PaymentLinkLog:
        session_id = uuid.uuid4().hex
        url = self.gateway.create_payment_link(amount_cents=amount_cents, session_id=session_id, recurring=recurring)
        log = PaymentLinkLog(session_id=session_id, customer_email=customer_email,
                             amount_cents=amount_cents, url=url)
        self._logs[session_id] = log
        self.email.send(to=customer_email, subject="Your Qiko payment link",
                        body=f"Complete your payment here:\n\n{url}")
        return log

    def update_status(self, session_id: str, status: str) -> PaymentLinkLog:
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status}")
        log = self._logs[session_id]
        log.status = status
        return log

    def mark_as_paid_for_user(self, customer_email: str) -> int:
        """Admin override: flip all of a customer's pending links to paid. Returns count changed."""
        changed = 0
        for log in self._logs.values():
            if log.customer_email == customer_email and log.status == "pending":
                log.status = "paid"
                changed += 1
        return changed

    def logs_for(self, customer_email: str) -> list[PaymentLinkLog]:
        return [x for x in self._logs.values() if x.customer_email == customer_email]
