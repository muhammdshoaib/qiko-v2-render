"""Admin customer directory: list with search/plan filters + per-customer earnings, a details
view, and soft-delete with email anonymisation. Aggregates from one source (the unified tables)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.admin.pagination import PAGE_SIZE, paginate
from app.modules.admin.sorting import CUSTOMER_SORTS, apply_sort


@dataclass
class CustomerRecord:
    user_id: str
    email: str
    plan: str = "free"
    stripe_paid_cents: int = 0
    local_paid_cents: int = 0
    agents: int = 0
    # Tenant user count. Already derivable in both implementations (the users table is loaded
    # anyway) but never surfaced, so "how many people are on this account" was unanswerable.
    users: int = 0
    conversations: int = 0
    is_studio: bool = False
    deleted: bool = False

    @property
    def earnings_cents(self) -> int:
        # Earnings = the higher of the two sources (Stripe vs local), reconciled to one number.
        return max(self.stripe_paid_cents, self.local_paid_cents)


@dataclass
class CustomerDirectory:
    _by_id: dict[str, CustomerRecord] = field(default_factory=dict)

    def add(self, rec: CustomerRecord) -> None:
        self._by_id[rec.user_id] = rec

    def count(self) -> int:
        """Total non-deleted customers, without the sort/paginate work list() does for its rows."""
        return sum(1 for r in self._by_id.values() if not r.deleted)

    def list(self, *, search: str | None = None, plan: str | None = None,
             page: int = 1, page_size: int = PAGE_SIZE,
             sort: str | None = None, order: str = "desc",
             sort_spec: dict | None = None) -> dict:
        rows = [r for r in self._by_id.values() if not r.deleted]
        if search:
            s = search.lower()
            rows = [r for r in rows if s in r.email.lower() or s in r.user_id.lower()]
        if plan and plan != "all":
            rows = [r for r in rows if r.plan == plan]
        # Highest earning first stays the default, because that is the order an operator scanning
        # the customer list actually wants. An explicit sort overrides it.
        rows.sort(key=lambda r: r.earnings_cents, reverse=True)
        rows = apply_sort(rows, sort_spec or CUSTOMER_SORTS, sort, order)
        return paginate(rows, page=page, page_size=page_size)

    def details(self, user_id: str) -> CustomerRecord | None:
        rec = self._by_id.get(user_id)
        return rec if rec and not rec.deleted else None

    def set_studio(self, user_id: str, enabled: bool) -> CustomerRecord:
        rec = self._by_id[user_id]
        rec.is_studio = enabled
        return rec

    def soft_delete(self, user_id: str) -> CustomerRecord:
        rec = self._by_id[user_id]
        rec.deleted = True
        rec.email = f"deleted+{user_id}@anonymized.invalid"  # anonymise PII
        return rec
