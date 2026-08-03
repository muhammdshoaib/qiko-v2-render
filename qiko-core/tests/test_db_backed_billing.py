"""Durable (Postgres-backed) billing stores, exercised on SQLite.

The billing services + admin Customers console are reached through synchronous route handlers
(FastAPI runs those in a threadpool), so their durable stores are synchronous
(app.db.sync_stores). These are the sync analogue of the async DB-backed store tests: each case
writes via one store instance, disposes the engine (simulating a redeploy/restart), then reads
back via a fresh store instance on the same on-disk DB.
"""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.sync_stores import (
    SqlInvoiceStore,
    SqlPaymentLinkStore,
    SqlSubscriptionStore,
)
from app.modules.billing.payment_links import PaymentLinkService
from app.modules.billing.subscriptions import SubscriptionService
from app.modules.billing.webhook import Invoice, StripeWebhookHandler
from app.modules.email.sender import ConsoleEmailSender


class _FakeStripe:
    def create_checkout_session(self, *, customer_id, price_id, promo, client_reference_id=None, plan=None):
        return f"https://checkout.stripe/{customer_id}/{price_id}"

    def billing_portal_url(self, *, customer_id):
        return f"https://portal.stripe/{customer_id}"


class _FakeLinkGateway:
    def create_payment_link(self, *, amount_cents, session_id, recurring):
        return f"https://pay.stripe/{session_id}?amt={amount_cents}"


def _sessionmaker(path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False), engine


def _reopen(path):
    return sessionmaker(create_engine(f"sqlite:///{path}"), expire_on_commit=False)


def test_subscriptions_persist_across_restart(tmp_path):
    path = tmp_path / "subs.db"
    sm1, e1 = _sessionmaker(path)
    svc1 = SubscriptionService(_FakeStripe(), store=SqlSubscriptionStore(sm1))
    svc1.link_customer("acme", "cus_123")     # tenant <-> Stripe customer mapping
    svc1.activate("acme", "pro")
    svc1.cancel("acme")                        # cancel_at_period_end, still active
    e1.dispose()                               # simulate redeploy/restart

    svc2 = SubscriptionService(_FakeStripe(), store=SqlSubscriptionStore(_reopen(path)))
    sub = svc2.status("acme")
    assert sub is not None
    assert sub.plan == "pro" and sub.status == "active" and sub.cancel_at_period_end is True
    # the customer mapping survived too
    assert svc2.stripe_customer_ref("acme") == "cus_123"
    assert svc2.summary() == {"active_subscriptions": 1, "by_plan": {"pro": 1}}
    # resume clears cancel_at_period_end and persists
    svc2.resume("acme")
    assert SqlSubscriptionStore(_reopen(path)).get("acme").cancel_at_period_end is False
    # unknown subject -> no subscription (tenant-scoped by key)
    assert svc2.status("other") is None


def test_invoices_persist_and_idempotent_across_restart(tmp_path):
    path = tmp_path / "inv.db"
    sm1, e1 = _sessionmaker(path)
    store1 = SqlInvoiceStore(sm1)
    assert store1.upsert(Invoice("in_1", "cus_1", 5000, "paid")) is True
    assert store1.upsert(Invoice("in_1", "cus_1", 5000, "paid")) is False   # idempotent by id
    assert store1.upsert(Invoice("in_2", "cus_2", 2000, "open")) is True
    e1.dispose()

    store2 = SqlInvoiceStore(_reopen(path))
    assert store2.count() == 2
    assert store2.get("in_1").amount_cents == 5000 and store2.get("in_1").status == "paid"
    assert [i.stripe_invoice_id for i in store2.list("cus_1")] == ["in_1"]
    assert store2.list("cus_missing") == []


def test_payment_links_persist_across_restart(tmp_path):
    path = tmp_path / "links.db"
    sm1, e1 = _sessionmaker(path)
    svc1 = PaymentLinkService(_FakeLinkGateway(), ConsoleEmailSender(), store=SqlPaymentLinkStore(sm1))
    svc1.create("buyer@x.com", 5000)                       # stays pending
    l2 = svc1.create("buyer@x.com", 2000)
    svc1.update_status(l2.session_id, "void")
    e1.dispose()

    svc2 = PaymentLinkService(_FakeLinkGateway(), ConsoleEmailSender(), store=SqlPaymentLinkStore(_reopen(path)))
    assert len(svc2.logs_for("buyer@x.com")) == 2
    assert svc2.mark_as_paid_for_user("buyer@x.com") == 1   # only the pending one flips
    assert sorted(x.status for x in svc2.logs_for("buyer@x.com")) == ["paid", "void"]
    assert svc2.logs_for("someone@else.com") == []


def test_webhook_syncs_invoice_and_activates_subscription_durably(tmp_path):
    path = tmp_path / "hook.db"
    sm, _ = _sessionmaker(path)
    subs = SubscriptionService(_FakeStripe(), store=SqlSubscriptionStore(sm))
    handler = StripeWebhookHandler(invoices=SqlInvoiceStore(sm), subscriptions=subs)

    assert handler.handle({"id": "evt_1", "type": "invoice.paid", "data": {"object": {
        "id": "in_9", "customer": "cus_9", "amount_paid": 4900, "status": "paid"}}}) == "invoice_synced"
    assert handler.handle({"id": "evt_2", "type": "checkout.session.completed", "data": {"object": {
        "client_reference_id": "acme", "customer": "cus_9",
        "metadata": {"plan": "pro"}}}}) == "subscription_activated"
    # duplicate delivery is ignored (idempotency guard) and does not re-sync
    assert handler.handle({"id": "evt_1", "type": "invoice.paid", "data": {"object": {}}}) == "duplicate"

    # everything landed in the durable store
    fresh = SqlSubscriptionStore(_reopen(path))
    assert fresh.get("acme").plan == "pro" and fresh.get("acme").status == "active"
    assert fresh.get_customer("acme") == "cus_9"
    assert SqlInvoiceStore(_reopen(path)).get("in_9").amount_cents == 4900


def test_migration_0024_imports_and_chains():
    path = (Path(__file__).resolve().parent.parent / "alembic" / "versions"
            / "0024_billing_durability_and_admin_customers.py")
    spec = importlib.util.spec_from_file_location("mig_0024", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0024_billing_durability"
    assert mod.down_revision == "0023_otp_and_pending_invites"
    assert callable(mod.upgrade) and callable(mod.downgrade)


def test_migration_0024_upgrade_creates_tables_on_sqlite(tmp_path):
    # A smoke check that the migration's DDL is valid: run upgrade() against a real (sqlite)
    # connection and confirm the tables it declares now exist.
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    path = (Path(__file__).resolve().parent.parent / "alembic" / "versions"
            / "0024_billing_durability_and_admin_customers.py")
    spec = importlib.util.spec_from_file_location("mig_0024_up", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
    tables = set(inspect(engine).get_table_names())
    assert {"billing_subscriptions", "billing_stripe_customers", "billing_invoices",
            "billing_payment_links", "admin_customer_flags"} <= tables


@pytest.mark.parametrize("bad_status", ["bogus", ""])
def test_payment_link_update_rejects_invalid_status(tmp_path, bad_status):
    sm, _ = _sessionmaker(tmp_path / f"pl_{bad_status or 'empty'}.db")
    svc = PaymentLinkService(_FakeLinkGateway(), ConsoleEmailSender(), store=SqlPaymentLinkStore(sm))
    log = svc.create("c@x.com", 1000)
    with pytest.raises(ValueError):
        svc.update_status(log.session_id, bad_status)
