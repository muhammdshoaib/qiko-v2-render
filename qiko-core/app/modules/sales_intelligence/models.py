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

# Per-source scheduled scan cadence (mirrors Ali's idg-sales SCAN_CADENCE_OPTIONS). "manual" means
# the source is never auto-scanned by the background scheduler; the operator runs it on demand.
SCAN_CADENCES = ("minutely", "hourly", "daily", "weekly", "manual")
# Cadence -> minutes between auto-scans. "manual" is deliberately absent (never auto-scan).
CADENCE_MINUTES = {"minutely": 1, "hourly": 60, "daily": 1440, "weekly": 10080}


def cadence_to_minutes(cadence: str | None, *, default: int) -> int | None:
    """Minutes between auto-scans for a source's cadence.

    Returns None for "manual" (never auto-scan). A known cadence maps to its fixed interval;
    anything else (e.g. a legacy "every_N_minutes" default) falls back to the caller's global
    `default` interval, so pre-existing sources keep their previous behaviour."""
    if cadence == "manual":
        return None
    return CADENCE_MINUTES.get(cadence or "", default)


STAGES = (
    "ingested", "qualifying", "qualified", "awaiting_review", "validated",
    "ready_salesforce", "push_pending", "pushed", "rejected", "push_failed",
)
# Stages a user may move an opportunity to directly (kanban drag / "Move to..." / "Run
# Qualification"). The Salesforce-driven stages (ready_salesforce, push_pending, pushed,
# push_failed) are deliberately excluded: reaching "pushed" must go through the real push action
# (push-to-salesforce), so they are never settable by a plain stage transition.
MANUAL_TRANSITION_STAGES = (
    "ingested", "qualifying", "qualified", "awaiting_review", "validated", "rejected",
)
RECOMMENDATIONS = ("Bid", "Review", "No Bid")
REVIEW_DECISIONS = ("approved", "rejected", "needs_review")
SALESFORCE_CONNECTION_STATUSES = ("connected", "expired", "error", "disconnected")
ACTIVITY_TYPES = ("opportunity", "source_status", "source_scan")

EDITABLE_OPPORTUNITY_FIELDS = (
    "title", "buyer", "country", "region", "category", "estimated_value", "currency",
    "published_at", "deadline_at", "source_url",
    # Qualification columns a manual editor may set/correct by hand (Ali's Qualification tab). When
    # `requalify` is requested these get overwritten by the scorer; otherwise the manual values stick.
    "recommendation", "qualification_score", "confidence",
)

# Extra manually-captured opportunity fields that don't have their own DB column. They are persisted
# inside Opportunity.raw_payload["manual"] (a JSON blob) so the manual "add/edit an opportunity" flow
# can round-trip Ali's richer form (OpportunityCreateView / OpportunityDetailView) WITHOUT a schema
# migration, and are surfaced back through OpportunityDetailService.build (overview/summary/
# qualification tabs). All optional; only `title` is required on create.
MANUAL_TEXT_FIELDS = (
    "reference", "notice_type", "security_clearance", "framework", "contract_duration",
    "technology", "executive_summary", "risk_summary", "opportunity_summary", "ai_reasoning",
)
MANUAL_LIST_FIELDS = ("requirements", "deliverables", "recommendations")
MANUAL_STRUCT_FIELDS = ("contacts", "links")
MANUAL_NUMERIC_FIELDS = ("extraction_confidence",)
MANUAL_DETAIL_FIELDS = MANUAL_TEXT_FIELDS + MANUAL_LIST_FIELDS + MANUAL_STRUCT_FIELDS + MANUAL_NUMERIC_FIELDS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_activity_type(action: str) -> str | None:
    """Same mapping as IdgSalesActivityLog::resolveActivityType (PHP)."""
    import re

    if action in ("source_enabled", "source_disabled", "source_cadence_changed"):
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
        """When this active source is next due to scan. One interval after its last scan (the same
        due-ness rule the scheduler uses: last_scan_at + interval), or -- if it has never scanned --
        the next interval boundary from now so a freshly-enabled source still shows a time rather
        than a blank. The interval is derived from the source's own `scan_cadence` (falling back to
        the global `scan_interval_minutes` for legacy cadences). Returns None for a disabled source
        or a "manual" cadence (nothing is auto-scheduled in either case)."""
        if not self.is_enabled():
            return None
        minutes = cadence_to_minutes(self.scan_cadence, default=scan_interval_minutes)
        if minutes is None:  # manual cadence -> never auto-scanned
            return None
        interval = max(1, minutes)
        if self.last_scan_at is not None:
            last = self.last_scan_at if self.last_scan_at.tzinfo else self.last_scan_at.replace(tzinfo=timezone.utc)
            return last + timedelta(minutes=interval)
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
    # Tracking half of a future calibration feedback loop: which verdict the IDG agentic
    # qualification pipeline reached for this opportunity, and which PipelineRun produced it.
    # Set by app.tasks.jobs.run_idg_qualification_pipeline whenever a run completes (not only on
    # "accept"). No auto-tuning reads these yet.
    pipeline_verdict: str | None = None
    pipeline_run_id: str | None = None
    # Set the moment _scan_source() enqueues run_idg_qualification_pipeline for this opportunity
    # (not on completion, unlike pipeline_verdict/pipeline_run_id above): the enqueue-cooldown gate
    # in OpportunityService._scan_source() reads this to skip re-enqueueing a fresh, expensive
    # pipeline run for an opportunity that already has one recent or in flight (QIW cost incident,
    # 2026-09-14 - a notice that stayed awaiting_review across per-minute re-scans got a full
    # Synthesizer/Critic Sonnet 4.5 run every single scan, unbounded).
    pipeline_last_enqueued_at: datetime | None = None
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


@dataclass
class IngestFilterSetting:
    """Persisted per-(tenant, agent) ingest filter. Defaults mirror deployed Staging: portal
    keyword search on with keyword 'security', and both allowlist bypasses on (scan everything)."""
    tenant: str
    agent_id: str
    query_enabled: bool = True
    query_keyword: str = "security"
    all_countries: bool = True
    all_categories: bool = True
    updated_at: datetime | None = None


class IngestionSourceStore(Protocol):
    async def get_or_create(self, tenant: str, agent_id: str, source_key: str, defaults: dict) -> IngestionSource: ...
    async def get(self, tenant: str, agent_id: str, source_key: str) -> IngestionSource | None: ...
    async def list_for_agent(self, tenant: str, agent_id: str) -> list[IngestionSource]: ...
    async def list_active(self, tenant: str | None = None) -> list[IngestionSource]: ...
    async def update(self, source: IngestionSource) -> IngestionSource: ...
    async def delete(self, tenant: str, agent_id: str, source_key: str) -> bool: ...


class OpportunityStore(Protocol):
    async def find_by_external_id(self, tenant: str, agent_id: str, source_key: str,
                                  external_id: str) -> Opportunity | None: ...
    async def add(self, opp: Opportunity) -> Opportunity: ...
    async def update(self, opp: Opportunity) -> Opportunity: ...
    async def get(self, tenant: str, agent_id: str, opp_id: str) -> Opportunity | None: ...
    async def list_for_agent(self, tenant: str, agent_id: str, **filters) -> list[Opportunity]: ...
    # Cross-tenant sweep used by the background deadline-reminder scheduler: every live (non-archived,
    # non-deleted) opportunity that carries a submission deadline, across all tenants/agents.
    async def list_with_deadline(self) -> list[Opportunity]: ...


class ActivityLogStore(Protocol):
    async def add(self, log: ActivityLog) -> ActivityLog: ...
    async def list_for_agent(self, tenant: str, agent_id: str, **filters) -> list[ActivityLog]: ...


class SalesforceConnectionStore(Protocol):
    async def get_or_create(self, tenant: str, agent_id: str) -> SalesforceConnection: ...
    async def update(self, conn: SalesforceConnection) -> SalesforceConnection: ...


class IngestFilterSettingStore(Protocol):
    async def get_or_create(self, tenant: str, agent_id: str) -> IngestFilterSetting: ...
    async def update(self, setting: IngestFilterSetting) -> IngestFilterSetting: ...


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

    async def delete(self, tenant: str, agent_id: str, source_key: str) -> bool:
        return self._by_key.pop((tenant, agent_id, source_key), None) is not None


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

    async def list_with_deadline(self) -> list[Opportunity]:
        return [o for o in self._by_id.values()
                if o.deadline_at is not None and not o.is_archived() and not o.is_deleted()]


def _apply_opportunity_filters(items: list[Opportunity], filters: dict) -> list[Opportunity]:
    stage = filters.get("stage")
    recommendation = filters.get("recommendation")
    source_key = filters.get("source_key")
    assigned_reviewer_user_id = filters.get("assigned_reviewer_user_id")
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
        if assigned_reviewer_user_id and o.assigned_reviewer_user_id != assigned_reviewer_user_id:
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
        if filters.get("actions"):
            allowed = set(filters["actions"])
            items = [log for log in items if log.action in allowed]
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


@dataclass
class InMemoryIngestFilterSettingStore:
    _by_key: dict[tuple[str, str], IngestFilterSetting] = field(default_factory=dict)

    async def get_or_create(self, tenant: str, agent_id: str) -> IngestFilterSetting:
        key = (tenant, agent_id)
        if key not in self._by_key:
            self._by_key[key] = IngestFilterSetting(tenant=tenant, agent_id=agent_id)
        return self._by_key[key]

    async def update(self, setting: IngestFilterSetting) -> IngestFilterSetting:
        self._by_key[(setting.tenant, setting.agent_id)] = setting
        return setting


def merge_ingest_filter(requested: dict, setting: IngestFilterSetting) -> dict:
    """Fill scan filters from the persisted per-agent ingest filter where the request omits them:
    the saved keyword (when query search is enabled) and the two allowlist bypasses ("*"). An
    explicit request value always wins. Used by both the manual scan endpoints and the scheduled
    sweep so automated and manual ingestion apply the same saved configuration."""
    merged = dict(requested)
    if "query" not in merged and setting.query_enabled and setting.query_keyword:
        merged["query"] = setting.query_keyword
    if "country_allowlist" not in merged and setting.all_countries:
        merged["country_allowlist"] = "*"
    if "category_allowlist" not in merged and setting.all_categories:
        merged["category_allowlist"] = "*"
    return merged
