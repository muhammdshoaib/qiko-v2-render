"""Port of:
 - app/Services/IdgSales/IdgSalesOpportunityService.php (sources, scan orchestration, dashboard)
 - app/Services/IdgSales/IdgSalesOpportunityMutationService.php (manual create/update/archive/
   restore/soft-delete)

Uses the same Protocol-based store injection as app.modules.crm.service, defaulting to in-memory
stores for dev/tests, swappable for Postgres-backed stores (app/db/stores.py) via app.state.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.modules.sales_intelligence.connectors import TedNoticeConnector, UngmNoticeConnector
from app.modules.sales_intelligence.models import (
    ActivityLog,
    ActivityLogStore,
    EDITABLE_OPPORTUNITY_FIELDS,
    IngestionSource,
    IngestionSourceStore,
    InMemoryActivityLogStore,
    InMemoryIngestionSourceStore,
    InMemoryOpportunityStore,
    Opportunity,
    OpportunityStore,
    SOURCE_KEYS,
    SOURCE_STATUSES,
)
from app.modules.sales_intelligence.qualification import QualificationService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class SalesIntelligenceError(Exception):
    pass


class SourceInactiveError(SalesIntelligenceError):
    pass


class OpportunityNotFoundError(SalesIntelligenceError):
    pass


def _default_source_cadence(scan_interval_minutes: int) -> str:
    return "every_1_minute" if scan_interval_minutes == 1 else f"every_{scan_interval_minutes}_minutes"


@dataclass
class OpportunityService:
    ungm: UngmNoticeConnector = field(default_factory=UngmNoticeConnector)
    ted: TedNoticeConnector = field(default_factory=TedNoticeConnector)
    qualification: QualificationService = field(default_factory=QualificationService)
    sources: IngestionSourceStore = None  # type: ignore[assignment]
    opportunities: OpportunityStore = None  # type: ignore[assignment]
    activity_logs: ActivityLogStore = None  # type: ignore[assignment]
    scan_interval_minutes: int = 1

    def __post_init__(self) -> None:
        if self.sources is None:
            self.sources = InMemoryIngestionSourceStore()
        if self.opportunities is None:
            self.opportunities = InMemoryOpportunityStore()
        if self.activity_logs is None:
            self.activity_logs = InMemoryActivityLogStore()

    async def _log(self, tenant: str, agent_id: str, action: str, detail: str, *, tone: str = "info",
                   opportunity_id: str | None = None, actor_user_id: str | None = None,
                   metadata: dict | None = None) -> ActivityLog:
        return await self.activity_logs.add(ActivityLog(
            id=_new_id(), tenant=tenant, agent_id=agent_id, action=action, detail=detail, tone=tone,
            opportunity_id=opportunity_id, actor_user_id=actor_user_id, metadata=metadata or {},
        ))

    async def ensure_sources(self, tenant: str, agent_id: str) -> None:
        await self.ensure_ungm_source(tenant, agent_id)
        await self.ensure_ted_source(tenant, agent_id)

    async def ensure_ungm_source(self, tenant: str, agent_id: str) -> IngestionSource:
        return await self.sources.get_or_create(tenant, agent_id, "ungm", {
            "name": "UNGM Public Notices", "type": "portal", "status": "inactive",
            "auth_status": "public_details_limited", "scan_cadence": _default_source_cadence(self.scan_interval_minutes),
            "config": {"url": "https://www.ungm.org/Public/Notice", "default_query": ""},
        })

    async def ensure_ted_source(self, tenant: str, agent_id: str) -> IngestionSource:
        return await self.sources.get_or_create(tenant, agent_id, "ted", {
            "name": "TED - EU Tenders", "type": "portal", "status": "inactive", "auth_status": "public_api",
            "scan_cadence": _default_source_cadence(self.scan_interval_minutes),
            "config": {"url": "https://ted.europa.eu/en/", "api_url": "https://api.ted.europa.eu/v3/notices/search"},
        })

    async def update_source_status(self, tenant: str, agent_id: str, source_key: str, status: str,
                                   actor_user_id: str | None = None) -> IngestionSource:
        if source_key not in SOURCE_KEYS:
            raise SalesIntelligenceError(f"invalid source_key: {source_key}")
        if status not in SOURCE_STATUSES:
            raise SalesIntelligenceError(f"invalid status: {status}")
        await self.ensure_sources(tenant, agent_id)
        source = await self.sources.get(tenant, agent_id, source_key)
        if source is None:
            raise OpportunityNotFoundError(f"source not found: {source_key}")
        previous = source.status
        source.status = status
        source.updated_at = _now()
        source = await self.sources.update(source)
        await self._log(tenant, agent_id, "source_enabled" if status == "active" else "source_disabled",
                        f"{source_key.upper()} set to {status} for this agent.",
                        tone="success" if status == "active" else "info", actor_user_id=actor_user_id,
                        metadata={"source_key": source_key, "previous_status": previous, "status": status})
        return source

    def assert_source_active(self, source: IngestionSource) -> None:
        if not source.is_enabled():
            raise SourceInactiveError(f"{source.source_key.upper()} is inactive for this agent. Enable it before scanning.")

    async def scan_ungm(self, tenant: str, agent_id: str, filters: dict, actor_user_id: str | None = None) -> dict:
        return await self._scan_source(tenant, agent_id, "ungm", "UNGM Public Notices",
                                        lambda: self.ungm.search(filters), actor_user_id)

    async def scan_ted(self, tenant: str, agent_id: str, filters: dict, actor_user_id: str | None = None) -> dict:
        return await self._scan_source(tenant, agent_id, "ted", "TED - EU Tenders",
                                        lambda: self.ted.search(filters), actor_user_id)

    async def _scan_source(self, tenant: str, agent_id: str, source_key: str, source_name: str,
                           search_fn, actor_user_id: str | None = None) -> dict:
        import asyncio

        source = await (self.ensure_ted_source(tenant, agent_id) if source_key == "ted"
                        else self.ensure_ungm_source(tenant, agent_id))
        self.assert_source_active(source)
        source.last_scan_status = "running"
        source.last_error = None
        await self.sources.update(source)

        try:
            result = await asyncio.to_thread(search_fn)
            upserted: list[Opportunity] = []
            created = 0
            updated = 0
            skipped = int(result.get("skipped", 0))

            for notice in result["notices"]:
                qualification = self.qualification.qualify(notice)
                external_id = notice.get("external_id") or _new_id()
                opportunity = await self.opportunities.find_by_external_id(tenant, agent_id, source_key, external_id)
                is_new = opportunity is None

                if not is_new:
                    if opportunity.is_archived() or opportunity.is_deleted():
                        continue
                    qualification = {k: v for k, v in qualification.items() if k != "stage"}
                else:
                    opportunity = Opportunity(id=_new_id(), tenant=tenant, agent_id=agent_id,
                                              external_id=external_id, source_key=source_key, source_name=source_name)

                opportunity.source_name = source_name
                opportunity.source_url = notice.get("source_url")
                opportunity.title = notice.get("title", "")
                opportunity.buyer = notice.get("buyer") or None
                opportunity.country = notice.get("country") or None
                opportunity.category = notice.get("category") or None
                opportunity.estimated_value = notice.get("estimated_value")
                opportunity.currency = notice.get("currency") or None
                opportunity.published_at = notice.get("published_at")
                opportunity.deadline_at = notice.get("deadline_at")
                opportunity.raw_payload = notice.get("raw") or {}
                for k, v in qualification.items():
                    setattr(opportunity, k, v)
                opportunity.updated_at = _now()

                opportunity = await (self.opportunities.add(opportunity) if is_new else self.opportunities.update(opportunity))
                created += 1 if is_new else 0
                updated += 0 if is_new else 1
                upserted.append(opportunity)

                await self._log(tenant, agent_id, "opportunity_ingested" if is_new else "opportunity_updated",
                                f"{'Ingested' if is_new else 'Updated'} {source_key.upper()} opportunity: {opportunity.title}",
                                tone="success", opportunity_id=opportunity.id, actor_user_id=actor_user_id,
                                metadata={"source_key": source_key, "external_id": external_id,
                                         "recommendation": opportunity.recommendation})

            source.last_scan_status = "success"
            source.last_scan_at = _now()
            source.opportunities_found = len(upserted)
            source.last_error = None
            source = await self.sources.update(source)

            await self._log(tenant, agent_id, f"{source_key}_scan_completed",
                            f"{source_key.upper()} scan completed with {len(upserted)} opportunities."
                            + (f" {skipped} notices skipped by ingest filters." if skipped else ""),
                            tone="success", actor_user_id=actor_user_id,
                            metadata={"source_key": source_key, "created": created, "updated": updated,
                                     "skipped": skipped, "payload": result.get("payload", {}),
                                     "total_notice_count": result.get("total_notice_count")})

            return {"source": source, "opportunities": upserted, "created": created, "updated": updated, "skipped": skipped}
        except SourceInactiveError:
            raise
        except Exception as e:
            source.last_scan_status = "failed"
            source.last_scan_at = _now()
            source.last_error = str(e)
            await self.sources.update(source)
            await self._log(tenant, agent_id, f"{source_key}_scan_failed", str(e), tone="danger",
                            actor_user_id=actor_user_id, metadata={"source_key": source_key})
            raise

    async def record_human_review(self, opportunity: Opportunity, decision: str, notes: str | None,
                                  actor_user_id: str | None) -> Opportunity:
        stage = {"approved": "validated", "rejected": "rejected"}.get(decision, "awaiting_review")
        opportunity.stage = stage
        opportunity.human_review_status = decision
        opportunity.human_review_notes = notes
        opportunity.reviewed_by_user_id = actor_user_id
        opportunity.reviewed_at = _now()
        opportunity.updated_at = _now()
        opportunity = await self.opportunities.update(opportunity)
        tone = {"approved": "success", "rejected": "warning"}.get(decision, "info")
        await self._log(opportunity.tenant, opportunity.agent_id, "human_review_recorded",
                        f"Human review decision recorded: {decision}", tone=tone, opportunity_id=opportunity.id,
                        actor_user_id=actor_user_id, metadata={"decision": decision})
        return opportunity

    async def update_notes(self, opportunity: Opportunity, notes: str | None, actor_user_id: str | None) -> Opportunity:
        opportunity.human_review_notes = notes
        opportunity.updated_at = _now()
        opportunity = await self.opportunities.update(opportunity)
        await self._log(opportunity.tenant, opportunity.agent_id, "opportunity_notes_updated",
                        "Opportunity notes updated." if notes else "Opportunity notes cleared.", tone="info",
                        opportunity_id=opportunity.id, actor_user_id=actor_user_id, metadata={"has_notes": bool(notes)})
        return opportunity

    async def dashboard_summary(self, tenant: str, agent_id: str) -> dict:
        opportunities = [o for o in await self.opportunities.list_for_agent(tenant, agent_id, include_archived=False)
                         if not o.is_archived()]

        def count(stage: str) -> int:
            return sum(1 for o in opportunities if o.stage == stage)

        return {
            "total": len(opportunities), "new": count("ingested"), "qualified": count("qualified"),
            "awaitingReview": count("awaiting_review"), "validated": count("validated"),
            "rejected": count("rejected"), "pushed": count("pushed"),
            "pipelineValue": sum(o.estimated_value or 0 for o in opportunities),
        }


@dataclass
class OpportunityMutationService:
    qualification: QualificationService = field(default_factory=QualificationService)
    opportunities: OpportunityStore = None  # type: ignore[assignment]
    activity_logs: ActivityLogStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.opportunities is None:
            self.opportunities = InMemoryOpportunityStore()
        if self.activity_logs is None:
            self.activity_logs = InMemoryActivityLogStore()

    async def _log(self, tenant: str, agent_id: str, opportunity_id: str, action: str, detail: str, *,
                   tone: str = "info", actor_user_id: str | None = None, metadata: dict | None = None) -> None:
        await self.activity_logs.add(ActivityLog(
            id=_new_id(), tenant=tenant, agent_id=agent_id, opportunity_id=opportunity_id, action=action,
            detail=detail, tone=tone, actor_user_id=actor_user_id, metadata=metadata or {},
        ))

    async def create_manual(self, tenant: str, agent_id: str, payload: dict, actor_user_id: str | None = None,
                            run_qualification: bool = True) -> Opportunity:
        source_key = (payload.get("source_key") or "manual").strip() or "manual"
        source_name = (payload.get("source_name") or "").strip() or (
            "Manual Entry" if source_key == "manual" else source_key.replace("_", " ").title())

        opportunity = Opportunity(
            id=_new_id(), tenant=tenant, agent_id=agent_id, external_id=f"manual-{uuid.uuid4()}",
            source_key=source_key, source_name=source_name, source_url=payload.get("source_url"),
            title=str(payload.get("title") or ""), buyer=payload.get("buyer"), country=payload.get("country"),
            region=payload.get("region"), category=payload.get("category"),
            estimated_value=payload.get("estimated_value"), currency=payload.get("currency"),
            published_at=payload.get("published_at"), deadline_at=payload.get("deadline_at"),
            stage=payload.get("stage") or "awaiting_review", salesforce_push_status="not_started",
            updated_by=actor_user_id, raw_payload={"origin": "manual", "created_by_user_id": actor_user_id},
        )

        if run_qualification:
            qualification = self.qualification.qualify({
                "title": opportunity.title, "buyer": opportunity.buyer, "country": opportunity.country,
                "category": opportunity.category, "estimated_value": opportunity.estimated_value,
                "currency": opportunity.currency, "deadline_at": opportunity.deadline_at,
                "source_url": opportunity.source_url,
            })
            qualification.pop("stage", None)
            for k, v in qualification.items():
                setattr(opportunity, k, v)
            if "stage" not in payload:
                opportunity.stage = "awaiting_review"

        opportunity = await self.opportunities.add(opportunity)
        await self._log(tenant, agent_id, opportunity.id, "opportunity_created_manual",
                        f"Manually created opportunity: {opportunity.title}", tone="success", actor_user_id=actor_user_id,
                        metadata={"source_key": source_key, "source_name": source_name,
                                 "external_id": opportunity.external_id, "run_qualification": run_qualification})
        return opportunity

    async def archive(self, opportunity: Opportunity, actor_user_id: str | None = None) -> Opportunity:
        if opportunity.is_archived():
            return opportunity
        opportunity.archived_at = _now()
        opportunity.archived_by = actor_user_id
        opportunity.updated_by = actor_user_id
        opportunity.updated_at = _now()
        opportunity = await self.opportunities.update(opportunity)
        await self._log(opportunity.tenant, opportunity.agent_id, opportunity.id, "opportunity_archived",
                        f"Opportunity archived: {opportunity.title}", tone="warning", actor_user_id=actor_user_id,
                        metadata={"stage": opportunity.stage})
        return opportunity

    async def restore(self, opportunity: Opportunity, actor_user_id: str | None = None) -> Opportunity:
        if not opportunity.is_archived():
            return opportunity
        opportunity.archived_at = None
        opportunity.archived_by = None
        opportunity.updated_by = actor_user_id
        opportunity.updated_at = _now()
        opportunity = await self.opportunities.update(opportunity)
        await self._log(opportunity.tenant, opportunity.agent_id, opportunity.id, "opportunity_restored",
                        f"Opportunity restored: {opportunity.title}", tone="success", actor_user_id=actor_user_id,
                        metadata={"stage": opportunity.stage})
        return opportunity

    async def soft_delete(self, opportunity: Opportunity, actor_user_id: str | None = None) -> Opportunity:
        opportunity.updated_by = actor_user_id
        opportunity.deleted_by = actor_user_id
        opportunity.deleted_at = _now()
        opportunity.updated_at = _now()
        opportunity = await self.opportunities.update(opportunity)
        await self._log(opportunity.tenant, opportunity.agent_id, opportunity.id, "opportunity_deleted",
                        f"Opportunity soft-deleted: {opportunity.title}", tone="warning", actor_user_id=actor_user_id,
                        metadata={"stage": opportunity.stage})
        return opportunity

    async def update_fields(self, opportunity: Opportunity, payload: dict, actor_user_id: str | None = None,
                            requalify: bool = False) -> Opportunity:
        changes: dict = {}
        for field_name in EDITABLE_OPPORTUNITY_FIELDS:
            if field_name not in payload:
                continue
            new_value = payload[field_name]
            old_value = getattr(opportunity, field_name)
            if self._values_equal(field_name, old_value, new_value):
                continue
            changes[field_name] = {"from": self._serialize(old_value), "to": self._serialize(new_value)}
            setattr(opportunity, field_name, new_value)

        if not changes and not requalify:
            return opportunity

        if changes:
            opportunity.updated_by = actor_user_id
        elif actor_user_id is not None:
            opportunity.updated_by = actor_user_id

        if requalify:
            qualification = self.qualification.qualify({
                "title": opportunity.title, "buyer": opportunity.buyer, "country": opportunity.country,
                "category": opportunity.category, "estimated_value": opportunity.estimated_value,
                "currency": opportunity.currency, "deadline_at": opportunity.deadline_at,
                "source_url": opportunity.source_url,
            })
            qualification.pop("stage", None)
            for k, v in qualification.items():
                setattr(opportunity, k, v)

        opportunity.updated_at = _now()
        opportunity = await self.opportunities.update(opportunity)

        if changes or requalify:
            await self._log(opportunity.tenant, opportunity.agent_id, opportunity.id, "opportunity_fields_updated",
                            (f"Opportunity fields updated: {', '.join(changes.keys())}" if changes
                             else "Opportunity re-qualified without field changes."),
                            tone="info", actor_user_id=actor_user_id, metadata={"changes": changes, "requalify": requalify})
        return opportunity

    def _values_equal(self, field_name: str, old, new) -> bool:
        if old is None and new is None:
            return True
        if old is None or new is None:
            return False
        if field_name == "estimated_value":
            return abs(float(old) - float(new)) < 0.001
        return old == new

    def _serialize(self, value):
        if isinstance(value, datetime):
            return value.isoformat()
        return value
