"""Domain dataclasses + store protocols for IDG Sales Intelligence.

Mirrors the shape of app.modules.crm.service (dataclass + Protocol + in-memory default store,
swappable for a Postgres-backed store behind the same protocol -- see app/db/stores.py).
Field names/types map 1:1 onto the Laravel migrations:
 - idg_sales_ingestion_sources  -> IngestionSource
 - idg_sales_opportunities      -> Opportunity
 - idg_sales_activity_logs      -> ActivityLog
 - idg_sales_salesforce_connections -> SalesforceConnection
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

SOURCE_KEYS = ("ungm", "ted")
SOURCE_STATUSES = ("active", "inactive")

STAGES = (
    "ingested", "qualifying", "qualified", "awaiting_review", "validated",
    "ready_salesforce", "push_pending", "pushed", "rejected", "push_failed",
)
RECOMMENDATIONS = ("Bid", "Review", "No Bid")
REVIEW_DECISIONS = ("approved", "rejected", "needs_review")
SALESFORCE_CONNECTION_STATUSES = ("connected", "expired", "error", "disconnected")
ACTIVITY_TYPES = ("opportunity", "source_status", "source_scan")

EDITABLE_OPPORTUNITY_FIELDS = (
    "title", "buyer", "country", "region", "category", "estimated_value", "currency",
    "published_at", "deadline_at", "source_url",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_activity_type(action: str) -> str | None:
    """Same mapping as IdgSalesActivityLog::resolveActivityType (PHP)."""
    import re

    if action in ("source_enabled", "source_disabled"):
        return "source_status"
    if re.match(r"^(ungm|ted)_scan_(completed|failed)$", action):
        return "source_scan"
    if action.startswith("opportunity_") or action == "human_review_recorded" or action.startswith("salesforce_push_"):
        return "opportunity"
    return None


@dataclass
class IngestionSource:
    id: str
    tenant: str
    agent_id: str
    source_key: str  # "ungm" | "ted"
    name: str
    type: str = "portal"
    status: str = "inactive"
    auth_status: str | None = None
    scan_cadence: str = "manual"
    last_scan_status: str | None = None
    last_scan_at: datetime | None = None
    opportunities_found: int = 0
    last_error: str | None = None
    config: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def is_enabled(self) -> bool:
        return self.status == "active"

    def next_scan_at(self, *, scan_interval_minutes: int, now: datetime | None = None) -> datetime | None:
        if not self.is_enabled():
            return None
        interval = max(1, scan_interval_minutes)
        cursor = (now or _now()).replace(second=0, microsecond=0)
        remainder = cursor.minute % interval
        if remainder == 0:
            return cursor + timedelta(minutes=interval)
        return cursor + timedelta(minutes=interval - remainder)


@dataclass
class Opportunity:
    id: str
    tenant: str
    agent_id: str
    external_id: str
    source_key: str
    source_name: str
    source_url: str | None = None
    title: str = ""
    buyer: str | None = None
    country: str | None = None
    region: str | None = None
    category: str | None = None
    estimated_value: float | None = None
    currency: str | None = None
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    stage: str = "ingested"
    recommendation: str | None = None
    qualification_score: int | None = None
    confidence: int | None = None
    competitor_readiness: str | None = None
    qualification_summary: str | None = None
    qualification_reasons: list[str] = field(default_factory=list)
    qualification_dimensions: dict = field(default_factory=dict)
    qualification_recommendations: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    human_review_status: str | None = None
    human_review_notes: str | None = None
    reviewed_by_user_id: str | None = None
    reviewed_at: datetime | None = None
    assigned_reviewer_user_id: str | None = None
    assigned_reviewer_name: str | None = None
    assigned_by_user_id: str | None = None
    assigned_at: datetime | None = None
    updated_by: str | None = None
    archived_at: datetime | None = None
    archived_by: str | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    salesforce_push_status: str = "not_started"
    salesforce_opportunity_id: str | None = None
    salesforce_pushed_at: datetime | None = None
    salesforce_push_error: str | None = None
    raw_payload: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def is_archived(self) -> bool:
        return self.archived_at is not None

    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@dataclass
class ActivityLog:
    id: str
    tenant: str
    agent_id: str
    action: str
    opportunity_id: str | None = None
    actor_user_id: str | None = None
    activity_type: str | None = None
    detail: str | None = None
    tone: str = "info"
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.activity_type and self.action:
            self.activity_type = resolve_activity_type(self.action)


@dataclass
class SalesforceConnection:
    tenant: str
    agent_id: str
    status: str = "disconnected"
    instance_url: str | None = None
    access_token: str | None = None  # encrypted at rest -- see salesforce.py
    refresh_token: str | None = None  # encrypted at rest -- see salesforce.py
    token_type: str | None = None
    token_expires_at: datetime | None = None
    salesforce_user_id: str | None = None
    salesforce_org_id: str | None = None
    connected_by_user_id: str | None = None
    last_error: str | None = None
    connected_at: datetime | None = None

    def is_connected(self) -> bool:
        return self.status == "connected" and bool(self.access_token) and bool(self.instance_url)


class IngestionSourceStore(Protocol):
    async def get_or_create(self, tenant: str, agent_id: str, source_key: str, defaults: dict) -> IngestionSource: ...
    async def get(self, tenant: str, agent_id: str, source_key: str) -> IngestionSource | None: ...
    async def list_for_agent(self, tenant: str, agent_id: str) -> list[IngestionSource]: ...
    async def list_active(self, tenant: str | None = None) -> list[IngestionSource]: ...
    async def update(self, source: IngestionSource) -> IngestionSource: ...


class OpportunityStore(Protocol):
    async def find_by_external_id(self, tenant: str, agent_id: str, source_key: str,
                                  external_id: str) -> Opportunity | None: ...
    async def add(self, opp: Opportunity) -> Opportunity: ...
    async def update(self, opp: Opportunity) -> Opportunity: ...
    async def get(self, tenant: str, agent_id: str, opp_id: str) -> Opportunity | None: ...
    async def list_for_agent(self, tenant: str, agent_id: str, **filters) -> list[Opportunity]: ...


class ActivityLogStore(Protocol):
    async def add(self, log: ActivityLog) -> ActivityLog: ...
    async def list_for_agent(self, tenant: str, agent_id: str, **filters) -> list[ActivityLog]: ...


class SalesforceConnectionStore(Protocol):
    async def get_or_create(self, tenant: str, agent_id: str) -> SalesforceConnection: ...
    async def update(self, conn: SalesforceConnection) -> SalesforceConnection: ...


@dataclass
class InMemoryIngestionSourceStore:
    _by_key: dict[tuple[str, str, str], IngestionSource] = field(default_factory=dict)

    async def get_or_create(self, tenant: str, agent_id: str, source_key: str, defaults: dict) -> IngestionSource:
        import uuid

        key = (tenant, agent_id, source_key)
        if key not in self._by_key:
            self._by_key[key] = IngestionSource(id=uuid.uuid4().hex[:12], tenant=tenant, agent_id=agent_id,
                                                source_key=source_key, **defaults)
        return self._by_key[key]

    async def get(self, tenant: str, agent_id: str, source_key: str) -> IngestionSource | None:
        return self._by_key.get((tenant, agent_id, source_key))

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[IngestionSource]:
        return [s for (t, a, _), s in self._by_key.items() if t == tenant and a == agent_id]

    async def list_active(self, tenant: str | None = None) -> list[IngestionSource]:
        return [s for s in self._by_key.values() if s.is_enabled() and (tenant is None or s.tenant == tenant)]

    async def update(self, source: IngestionSource) -> IngestionSource:
        self._by_key[(source.tenant, source.agent_id, source.source_key)] = source
        return source


@dataclass
class InMemoryOpportunityStore:
    _by_id: dict[str, Opportunity] = field(default_factory=dict)

    async def find_by_external_id(self, tenant: str, agent_id: str, source_key: str,
                                  external_id: str) -> Opportunity | None:
        for o in self._by_id.values():
            if (o.tenant == tenant and o.agent_id == agent_id and o.source_key == source_key
                    and o.external_id == external_id):
                return o
        return None

    async def add(self, opp: Opportunity) -> Opportunity:
        self._by_id[opp.id] = opp
        return opp

    async def update(self, opp: Opportunity) -> Opportunity:
        self._by_id[opp.id] = opp
        return opp

    async def get(self, tenant: str, agent_id: str, opp_id: str) -> Opportunity | None:
        o = self._by_id.get(opp_id)
        return o if o and o.tenant == tenant and o.agent_id == agent_id else None

    async def list_for_agent(self, tenant: str, agent_id: str, **filters) -> list[Opportunity]:
        items = [o for o in self._by_id.values() if o.tenant == tenant and o.agent_id == agent_id]
        return _apply_opportunity_filters(items, filters)


def _apply_opportunity_filters(items: list[Opportunity], filters: dict) -> list[Opportunity]:
    stage = filters.get("stage")
    recommendation = filters.get("recommendation")
    source_key = filters.get("source_key")
    title = (filters.get("title") or "").lower()
    search = (filters.get("search") or "").lower()
    include_archived = filters.get("include_archived", False)
    archived_only = filters.get("archived_only", False)

    def keep(o: Opportunity) -> bool:
        if o.is_deleted():
            return False
        if stage and o.stage != stage:
            return False
        if recommendation and o.recommendation != recommendation:
            return False
        if source_key and o.source_key != source_key:
            return False
        if title and title not in (o.title or "").lower():
            return False
        if search and not any(search in (v or "").lower() for v in (o.title, o.buyer, o.country, o.category)):
            return False
        if archived_only and not o.is_archived():
            return False
        if not archived_only and not include_archived and o.is_archived():
            return False
        return True

    result = [o for o in items if keep(o)]
    result.sort(key=lambda o: (o.deadline_at is None, o.deadline_at or _now()))
    result.sort(key=lambda o: o.updated_at, reverse=True)
    return result


@dataclass
class InMemoryActivityLogStore:
    _by_id: dict[str, ActivityLog] = field(default_factory=dict)
    _seq: int = 0

    async def add(self, log: ActivityLog) -> ActivityLog:
        self._by_id[log.id] = log
        return log

    async def list_for_agent(self, tenant: str, agent_id: str, **filters) -> list[ActivityLog]:
        items = [log for log in self._by_id.values() if log.tenant == tenant and log.agent_id == agent_id]
        if filters.get("opportunity_id"):
            items = [log for log in items if log.opportunity_id == filters["opportunity_id"]]
        if filters.get("activity_type"):
            items = [log for log in items if log.activity_type == filters["activity_type"]]
        if filters.get("action"):
            items = [log for log in items if log.action == filters["action"]]
        items.sort(key=lambda log: log.created_at, reverse=True)
        limit = filters.get("limit")
        return items[:limit] if limit else items


@dataclass
class InMemorySalesforceConnectionStore:
    _by_key: dict[tuple[str, str], SalesforceConnection] = field(default_factory=dict)

    async def get_or_create(self, tenant: str, agent_id: str) -> SalesforceConnection:
        key = (tenant, agent_id)
        if key not in self._by_key:
            self._by_key[key] = SalesforceConnection(tenant=tenant, agent_id=agent_id)
        return self._by_key[key]

    async def update(self, conn: SalesforceConnection) -> SalesforceConnection:
        self._by_key[(conn.tenant, conn.agent_id)] = conn
        return conn
