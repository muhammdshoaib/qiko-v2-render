"""Synchronous Postgres-backed stores for the billing lifecycle + the admin Customers console.

These are the durable replacements for the in-memory billing state (subscriptions + the
tenant<->Stripe-customer mapping, synced invoices, payment-link logs) and for the admin customer
directory. They are SYNCHRONOUS on purpose: the billing/admin endpoints that use them are
synchronous `def` route handlers (FastAPI runs those in a worker threadpool, so a blocking DB
call is safe there) and the in-memory services they replace expose a synchronous interface. They
are drop-in behind the same interfaces, so no route or service signature changes.

They are wired in app.main.lifespan under USE_DB_STORES, exactly like the async SqlChatStore /
SqlTeamsStore / ... are wired for the async side of the app. The admin customer directory is
DERIVED from the real tenants/users/agents/subscriptions (no parallel store to drift): the only
admin-set state with its own row is the per-tenant Studio/soft-delete flag.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AdminCustomerFlag as FlagRow
from app.db.models import Agent as AgentRow
from app.db.models import BillingInvoice as InvoiceRow
from app.db.models import BillingPaymentLink as PaymentLinkRow
from app.db.models import BillingStripeCustomer as StripeCustomerRow
from app.db.models import BillingSubscription as SubscriptionRow
from app.db.models import SlackInstallation as SlackInstallationRow
from app.db.models import Tenant as TenantRow
from app.db.models import User as UserRow
from app.core.crypto import decrypt, encrypt
from app.modules.admin.customers import CustomerRecord
from app.modules.channels.slack_oauth import SlackInstallation
from app.modules.admin.pagination import PAGE_SIZE, paginate
from app.modules.admin.sorting import CUSTOMER_SORTS, apply_sort
from app.modules.billing.payment_links import PaymentLinkLog
from app.modules.billing.subscriptions import Subscription
from app.modules.billing.webhook import Invoice

_PAID_INVOICE_STATUSES = {"paid"}
_OWNER_ROLES = {"owner", "admin"}


def _subscription_from_row(r: SubscriptionRow) -> Subscription:
    return Subscription(customer_id=r.subject, plan=r.plan, status=r.status,
                        cancel_at_period_end=r.cancel_at_period_end)


@dataclass
class SqlSubscriptionStore:
    """Durable subscription state (subscriptions + the tenant<->Stripe-customer mapping) behind
    the SubscriptionStore protocol -- previously in-memory only, so a tenant's plan/status was
    wiped on every restart."""
    sessionmaker: sessionmaker[Session]

    def get(self, subject: str) -> Subscription | None:
        with self.sessionmaker() as s:
            row = s.get(SubscriptionRow, subject)
            return _subscription_from_row(row) if row is not None else None

    def put(self, sub: Subscription) -> None:
        with self.sessionmaker() as s, s.begin():
            row = s.get(SubscriptionRow, sub.customer_id)
            if row is None:
                s.add(SubscriptionRow(subject=sub.customer_id, plan=sub.plan, status=sub.status,
                                      cancel_at_period_end=sub.cancel_at_period_end))
            else:
                row.plan = sub.plan
                row.status = sub.status
                row.cancel_at_period_end = sub.cancel_at_period_end

    def all(self) -> list[Subscription]:
        with self.sessionmaker() as s:
            rows = s.execute(select(SubscriptionRow)).scalars().all()
            return [_subscription_from_row(r) for r in rows]

    def get_customer(self, tenant: str) -> str | None:
        with self.sessionmaker() as s:
            row = s.get(StripeCustomerRow, tenant)
            return row.stripe_customer_id if row is not None else None

    def set_customer(self, tenant: str, stripe_customer_id: str) -> None:
        with self.sessionmaker() as s, s.begin():
            row = s.get(StripeCustomerRow, tenant)
            if row is None:
                s.add(StripeCustomerRow(tenant_id=tenant, stripe_customer_id=stripe_customer_id))
            else:
                row.stripe_customer_id = stripe_customer_id


def _invoice_from_row(r: InvoiceRow) -> Invoice:
    return Invoice(stripe_invoice_id=r.stripe_invoice_id, customer_id=r.customer_id,
                   amount_cents=r.amount_cents, status=r.status)


@dataclass
class SqlInvoiceStore:
    """Durable Stripe-invoice sync behind the same interface as the in-memory InvoiceStore --
    idempotent by stripe_invoice_id, so a re-delivered webhook never double-counts."""
    sessionmaker: sessionmaker[Session]

    def upsert(self, inv: Invoice) -> bool:
        """Idempotent by stripe_invoice_id. Returns True if newly inserted, False if updated."""
        with self.sessionmaker() as s, s.begin():
            row = s.get(InvoiceRow, inv.stripe_invoice_id)
            is_new = row is None
            if is_new:
                s.add(InvoiceRow(stripe_invoice_id=inv.stripe_invoice_id, customer_id=inv.customer_id,
                                 amount_cents=inv.amount_cents, status=inv.status))
            else:
                row.customer_id = inv.customer_id
                row.amount_cents = inv.amount_cents
                row.status = inv.status
            return is_new

    def get(self, invoice_id: str) -> Invoice | None:
        with self.sessionmaker() as s:
            row = s.get(InvoiceRow, invoice_id)
            return _invoice_from_row(row) if row is not None else None

    def count(self) -> int:
        with self.sessionmaker() as s:
            return int(s.execute(select(func.count()).select_from(InvoiceRow)).scalar_one())

    def list(self, customer_id: str | None = None) -> list[Invoice]:
        with self.sessionmaker() as s:
            q = select(InvoiceRow)
            if customer_id is not None:
                q = q.where(InvoiceRow.customer_id == customer_id)
            rows = s.execute(q).scalars().all()
            return [_invoice_from_row(r) for r in rows]


def _payment_link_from_row(r: PaymentLinkRow) -> PaymentLinkLog:
    return PaymentLinkLog(session_id=r.session_id, customer_email=r.customer_email,
                          amount_cents=r.amount_cents, url=r.url, status=r.status)


@dataclass
class SqlPaymentLinkStore:
    """Durable payment-link log behind the PaymentLinkStore protocol -- previously in-memory only,
    so a link (and its paid/void status) was lost on a restart."""
    sessionmaker: sessionmaker[Session]

    def add(self, log: PaymentLinkLog) -> None:
        with self.sessionmaker() as s, s.begin():
            s.add(PaymentLinkRow(session_id=log.session_id, customer_email=log.customer_email,
                                 amount_cents=log.amount_cents, url=log.url, status=log.status))

    def get(self, session_id: str) -> PaymentLinkLog | None:
        with self.sessionmaker() as s:
            row = s.get(PaymentLinkRow, session_id)
            return _payment_link_from_row(row) if row is not None else None

    def set_status(self, session_id: str, status: str) -> None:
        with self.sessionmaker() as s, s.begin():
            row = s.get(PaymentLinkRow, session_id)
            if row is None:
                raise KeyError(session_id)  # matches the in-memory dict-access behaviour
            row.status = status

    def list_for_email(self, customer_email: str) -> list[PaymentLinkLog]:
        with self.sessionmaker() as s:
            rows = s.execute(select(PaymentLinkRow).where(
                PaymentLinkRow.customer_email == customer_email)).scalars().all()
            return [_payment_link_from_row(r) for r in rows]

    def mark_pending_paid_for_email(self, customer_email: str) -> int:
        with self.sessionmaker() as s, s.begin():
            rows = s.execute(select(PaymentLinkRow).where(
                PaymentLinkRow.customer_email == customer_email,
                PaymentLinkRow.status == "pending")).scalars().all()
            for row in rows:
                row.status = "paid"
            return len(rows)


@dataclass
class SqlCustomerDirectory:
    """The admin Customers console, DERIVED from the real data instead of a parallel store.

    A "customer" is a tenant. Each row aggregates the tenant's real users (count + the owner
    email shown as the customer's identity), workers (agent count), plan/status (its
    subscription) and earnings (sum of its paid invoices). The only admin-set state with its own
    durable row is the per-tenant Studio-access + soft-delete flag (AdminCustomerFlag).

    Exposes the same interface as the in-memory CustomerDirectory, so the admin router is
    unchanged: list/details return CustomerRecord objects, and set_studio/soft_delete raise
    KeyError for an unknown tenant (which the router turns into a 404)."""
    sessionmaker: sessionmaker[Session]

    def _records(self, s: Session) -> dict[str, CustomerRecord]:
        tenants = s.execute(select(TenantRow)).scalars().all()
        users = s.execute(select(UserRow)).scalars().all()
        agents = s.execute(select(AgentRow.tenant_id)).scalars().all()
        subs = {r.subject: r for r in s.execute(select(SubscriptionRow)).scalars().all()}
        custmap = {r.tenant_id: r.stripe_customer_id
                   for r in s.execute(select(StripeCustomerRow)).scalars().all()}
        invoices = s.execute(select(InvoiceRow)).scalars().all()
        flags = {r.tenant_id: r for r in s.execute(select(FlagRow)).scalars().all()}

        owner_email: dict[str, str] = {}
        owner_is_privileged: dict[str, bool] = {}
        for u in users:
            if not u.tenant_id:
                continue
            # Shown identity = an owner/admin's email if the tenant has one, else any user's email
            # (first seen wins within each tier).
            privileged = u.role in _OWNER_ROLES
            if u.tenant_id not in owner_email or (privileged and not owner_is_privileged.get(u.tenant_id)):
                owner_email[u.tenant_id] = u.email
                owner_is_privileged[u.tenant_id] = privileged

        worker_count: dict[str, int] = {}
        for tid in agents:
            worker_count[tid] = worker_count.get(tid, 0) + 1

        user_count: dict[str, int] = {}
        for u in users:
            if u.tenant_id:
                user_count[u.tenant_id] = user_count.get(u.tenant_id, 0) + 1

        earnings: dict[str, int] = {}
        # Invoices are keyed by Stripe customer id; map each tenant's paid invoices back to it via
        # the tenant<->customer mapping (falling back to the tenant string, our stable ref).
        cust_to_tenant = {v: k for k, v in custmap.items()}
        for inv in invoices:
            if inv.status not in _PAID_INVOICE_STATUSES:
                continue
            tenant = cust_to_tenant.get(inv.customer_id, inv.customer_id)
            earnings[tenant] = earnings.get(tenant, 0) + int(inv.amount_cents or 0)

        records: dict[str, CustomerRecord] = {}
        for t in tenants:
            sub = subs.get(t.id)
            flag = flags.get(t.id)
            records[t.id] = CustomerRecord(
                user_id=t.id,
                email=owner_email.get(t.id) or t.name,
                plan=sub.plan if sub is not None and sub.status == "active" else "free",
                stripe_paid_cents=earnings.get(t.id, 0),
                local_paid_cents=0,
                agents=worker_count.get(t.id, 0),
                users=user_count.get(t.id, 0),
                is_studio=bool(flag.is_studio) if flag is not None else False,
                deleted=bool(flag.deleted) if flag is not None else False)
        return records

    def list(self, *, search: str | None = None, plan: str | None = None,
             page: int = 1, page_size: int = PAGE_SIZE,
             sort: str | None = None, order: str = "desc",
             sort_spec: dict | None = None) -> dict:
        with self.sessionmaker() as s:
            rows = [r for r in self._records(s).values() if not r.deleted]
        if search:
            q = search.lower()
            rows = [r for r in rows if q in r.email.lower() or q in r.user_id.lower()]
        if plan and plan != "all":
            rows = [r for r in rows if r.plan == plan]
        # Highest earning first stays the default, because that is the order an operator scanning
        # the customer list actually wants. An explicit sort overrides it.
        rows.sort(key=lambda r: r.earnings_cents, reverse=True)
        rows = apply_sort(rows, sort_spec or CUSTOMER_SORTS, sort, order)
        return paginate(rows, page=page, page_size=page_size)

    def details(self, user_id: str) -> CustomerRecord | None:
        with self.sessionmaker() as s:
            rec = self._records(s).get(user_id)
        return rec if rec is not None and not rec.deleted else None

    def set_studio(self, user_id: str, enabled: bool) -> CustomerRecord:
        with self.sessionmaker() as s, s.begin():
            if s.get(TenantRow, user_id) is None:
                raise KeyError(user_id)
            flag = s.get(FlagRow, user_id)
            if flag is None:
                s.add(FlagRow(tenant_id=user_id, is_studio=enabled))
            else:
                flag.is_studio = enabled
        with self.sessionmaker() as s:
            return self._records(s)[user_id]

    def soft_delete(self, user_id: str) -> CustomerRecord:
        with self.sessionmaker() as s, s.begin():
            if s.get(TenantRow, user_id) is None:
                raise KeyError(user_id)
            flag = s.get(FlagRow, user_id)
            if flag is None:
                s.add(FlagRow(tenant_id=user_id, deleted=True))
            else:
                flag.deleted = True
        with self.sessionmaker() as s:
            rec = self._records(s)[user_id]
        # Anonymise the PII in the response (the tenant's real data stays intact; the record is
        # now excluded from list/details). Mirrors the in-memory CustomerDirectory behaviour.
        rec.email = f"deleted+{user_id}@anonymized.invalid"
        return rec


@dataclass
class SqlSlackInstallationStore:
    """Durable Slack OAuth installations behind the same interface as the in-memory
    InstallationStore -- previously in-memory only, so every OAuth-installed workspace was lost
    on restart and the arq worker (a different process from the API that ran the callback) could
    never resolve a bot token at all, which made the digest undeliverable in production.

    Synchronous for the same reason as the billing stores above: the existing call sites
    (`SlackOAuth.complete_install`, `/channels/slack/send`) are synchronous, so this stays a
    drop-in and no route or service signature changes.

    The bot token is Fernet-encrypted at rest and decrypted only on the way out, exactly as the
    in-memory store does.
    """
    sessionmaker: sessionmaker[Session]

    @staticmethod
    def _to_domain(row: SlackInstallationRow) -> SlackInstallation:
        return SlackInstallation(
            team_id=row.team_id, bot_token=decrypt(row.bot_token_encrypted),
            bot_user_id=row.bot_user_id,
            enterprise_id=None if row.enterprise_id == "-" else row.enterprise_id,
            installed_by=row.installed_by, tenant=row.tenant_id, worker_id=row.worker_id)

    def save(self, inst: SlackInstallation) -> None:
        # A tenantless installation is refused rather than stored under tenant_id="". Such a row
        # cannot be attributed to anyone, is excluded from fetch_by_workspace anyway, and its only
        # effect would be to hold a live bot token that no tenant owns.
        if not inst.tenant:
            raise ValueError("a Slack installation must belong to a tenant")
        with self.sessionmaker() as s, s.begin():
            key = (inst.team_id, inst.enterprise_id or "-", inst.tenant or "")
            row = s.get(SlackInstallationRow, key)
            ciphertext = encrypt(inst.bot_token)
            if row is None:
                s.add(SlackInstallationRow(
                    team_id=inst.team_id, enterprise_id=inst.enterprise_id or "-",
                    tenant_id=inst.tenant or "", bot_token_encrypted=ciphertext,
                    bot_user_id=inst.bot_user_id, worker_id=inst.worker_id,
                    installed_by=inst.installed_by))
            else:
                row.bot_token_encrypted = ciphertext
                row.bot_user_id = inst.bot_user_id
                row.worker_id = inst.worker_id
                row.installed_by = inst.installed_by

    def fetch(self, team_id: str, enterprise_id: str | None = None,
              tenant: str | None = None) -> SlackInstallation | None:
        with self.sessionmaker() as s:
            row = s.get(SlackInstallationRow, (team_id, enterprise_id or "-", tenant or ""))
            return self._to_domain(row) if row is not None else None

    def delete(self, team_id: str, enterprise_id: str | None = None,
               tenant: str | None = None) -> None:
        with self.sessionmaker() as s, s.begin():
            row = s.get(SlackInstallationRow, (team_id, enterprise_id or "-", tenant or ""))
            if row is not None:
                s.delete(row)

    def fetch_by_workspace(self, team_id: str,
                           enterprise_id: str | None = None) -> SlackInstallation | None:
        """Reverse lookup for the Events API, which knows the workspace but not the Qiko tenant.

        Returns None when the workspace maps to zero or to MORE THAN ONE tenant. A workspace
        installed by two tenants has no single correct answer, and answering anyway would write a
        third party's Slack messages into whichever tenant the query happened to return first.
        Installations with no tenant are excluded for the same reason.
        """
        with self.sessionmaker() as s:
            rows = s.execute(
                select(SlackInstallationRow).where(
                    SlackInstallationRow.team_id == team_id,
                    SlackInstallationRow.enterprise_id == (enterprise_id or "-"),
                    SlackInstallationRow.tenant_id != "",
                ).limit(2)
            ).scalars().all()
            return self._to_domain(rows[0]) if len(rows) == 1 else None

    def find_for_worker(self, tenant: str, worker_id: str) -> SlackInstallation | None:
        """Return the single Slack installation for a worker, or None if there is not exactly one."""
        with self.sessionmaker() as s:
            rows = s.execute(
                select(SlackInstallationRow).where(
                    SlackInstallationRow.tenant_id == tenant,
                    SlackInstallationRow.worker_id == worker_id,
                ).limit(2)
            ).scalars().all()
            return self._to_domain(rows[0]) if len(rows) == 1 else None
