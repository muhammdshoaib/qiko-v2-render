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
    MANUAL_TRANSITION_STAGES,
    Opportunity,
    OpportunityStore,
    SCAN_CADENCES,
    SOURCE_KEYS,
    SOURCE_STATUSES,
)
from app.modules.sales_intelligence.notifications import SalesNotificationService
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


class InvalidStageTransitionError(SalesIntelligenceError):
    pass


# Map a global scan interval onto one of the per-source cadence values (SCAN_CADENCES) where it
# lines up exactly, so a freshly-provisioned source has a cadence the UI select can render. Any
# other interval keeps the legacy "every_N_minutes" label, which cadence_to_minutes falls back to.
_INTERVAL_TO_CADENCE = {1: "minutely", 60: "hourly", 1440: "daily", 10080: "weekly"}


def _default_source_cadence(scan_interval_minutes: int) -> str:
    return _INTERVAL_TO_CADENCE.get(scan_interval_minutes, f"every_{scan_interval_minutes}_minutes")


@dataclass
class OpportunityService:
    ungm: UngmNoticeConnector = field(default_factory=UngmNoticeConnector)
    ted: TedNoticeConnector = field(default_factory=TedNoticeConnector)
    qualification: QualificationService = field(default_factory=QualificationService)
    sources: IngestionSourceStore = None  # type: ignore[assignment]
    opportunities: OpportunityStore = None  # type: ignore[assignment]
    activity_logs: ActivityLogStore = None  # type: ignore[assignment]
    notifier: SalesNotificationService | None = None
    # Optional agent resolver (AgentService/AgentStore with async get(tenant, agent_id) -> agent
    # with a `.config` dict). When set, per-agent si_* config drives qualification even for the
    # scheduler/background scan path; the manual API path passes agent_config explicitly instead.
    agents: object | None = None
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

    async def update_source_cadence(self, tenant: str, agent_id: str, source_key: str, cadence: str,
                                    actor_user_id: str | None = None) -> IngestionSource:
        """Set a portal source's scheduled scan cadence (minutely/hourly/daily/weekly/manual). The
        scheduler derives each source's due interval from this, so "manual" turns off auto-scans."""
        if source_key not in SOURCE_KEYS:
            raise SalesIntelligenceError(f"invalid source_key: {source_key}")
        if cadence not in SCAN_CADENCES:
            raise SalesIntelligenceError(f"invalid scan_cadence: {cadence}")
        await self.ensure_sources(tenant, agent_id)
        source = await self.sources.get(tenant, agent_id, source_key)
        if source is None:
            raise OpportunityNotFoundError(f"source not found: {source_key}")
        previous = source.scan_cadence
        source.scan_cadence = cadence
        source.updated_at = _now()
        source = await self.sources.update(source)
        await self._log(tenant, agent_id, "source_cadence_changed",
                        f"{source_key.upper()} scan cadence set to {cadence} for this agent.",
                        tone="info", actor_user_id=actor_user_id,
                        metadata={"source_key": source_key, "previous_cadence": previous, "scan_cadence": cadence})
        return source

    def assert_source_active(self, source: IngestionSource) -> None:
        if not source.is_enabled():
            raise SourceInactiveError(f"{source.source_key.upper()} is inactive for this agent. Enable it before scanning.")

    async def scan_ungm(self, tenant: str, agent_id: str, filters: dict, actor_user_id: str | None = None,
                        agent_config: dict | None = None) -> dict:
        return await self._scan_source(tenant, agent_id, "ungm", "UNGM Public Notices",
                                        lambda: self.ungm.search(filters), actor_user_id, agent_config)

    async def scan_ted(self, tenant: str, agent_id: str, filters: dict, actor_user_id: str | None = None,
                       agent_config: dict | None = None) -> dict:
        return await self._scan_source(tenant, agent_id, "ted", "TED - EU Tenders",
                                        lambda: self.ted.search(filters), actor_user_id, agent_config)

    async def _resolve_scorer(self, tenant: str, agent_id: str,
                              agent_config: dict | None) -> QualificationService:
        """Build the per-agent qualification scorer. Uses an explicitly-passed agent_config (from
        the manual API path) or, failing that, resolves the agent via the optional `agents` store
        (scheduler/background path). Falls back to the default IDG scorer when neither is available."""
        if agent_config is None and self.agents is not None:
            agent = await self.agents.get(tenant, agent_id)
            agent_config = getattr(agent, "config", None) if agent is not None else None
        return self.qualification.with_config(agent_config)

    async def _scan_source(self, tenant: str, agent_id: str, source_key: str, source_name: str,
                           search_fn, actor_user_id: str | None = None,
                           agent_config: dict | None = None) -> dict:
        import asyncio

        source = await (self.ensure_ted_source(tenant, agent_id) if source_key == "ted"
                        else self.ensure_ungm_source(tenant, agent_id))
        self.assert_source_active(source)
        source.last_scan_status = "running"
        source.last_error = None
        await self.sources.update(source)

        scorer = await self._resolve_scorer(tenant, agent_id, agent_config)

        try:
            result = await asyncio.to_thread(search_fn)
            upserted: list[Opportunity] = []
            created = 0
            updated = 0
            skipped = int(result.get("skipped", 0))

            for notice in result["notices"]:
                qualification = scorer.qualify(notice)
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

                # Notification trigger: a freshly-ingested opportunity that needs human validation.
                if is_new and self.notifier is not None and opportunity.stage == "awaiting_review":
                    await self.notifier.notify_review_required(opportunity)

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
            # Notification trigger: scan failed.
            if self.notifier is not None:
                await self.notifier.notify_scan_failed(tenant, agent_id, source_key, str(e))
            raise

    async def send_deadline_reminder(self, opportunity: Opportunity, due_in_days: int) -> None:
        """Deadline-reminder notification trigger -- a thin hook the scheduler can call later
        (mirrors IdgSalesDeadlineReminderService). No-op if no notifier is wired."""
        if self.notifier is not None:
            await self.notifier.notify_deadline_reminder(opportunity, due_in_days)

    async def record_deadline_reminder(self, opportunity: Opportunity, due_in_days: int) -> ActivityLog:
        """Fire the deadline reminder AND persist the audit/dedupe marker in one step -- used by the
        background scheduler sweep (app.modules.sales_intelligence.scheduler). The activity-log row
        (action `opportunity_deadline_reminded`) doubles as the "already reminded today" marker, so
        the sweep needs no extra schema. `send_deadline_reminder` stays a pure notification hook."""
        await self.send_deadline_reminder(opportunity, due_in_days)
        return await self._log(
            opportunity.tenant, opportunity.agent_id, "opportunity_deadline_reminded",
            f"Deadline reminder sent -- {due_in_days} day(s) until submission deadline.",
            tone="info", opportunity_id=opportunity.id,
            metadata={"dueInDays": due_in_days,
                      "deadlineAt": opportunity.deadline_at.isoformat() if opportunity.deadline_at else None})

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

    async def transition_stage(self, opportunity: Opportunity, stage: str,
                               actor_user_id: str | None = None) -> Opportunity:
        """Move an opportunity to a manual/pipeline stage (kanban drag, keyboard "Move to...",
        or the "Run Qualification" action which sets `qualifying`). Only the manual stages are
        allowed here -- the Salesforce-driven stages (pushed etc.) must go through their own
        action endpoints, so this refuses them rather than silently corrupting the pipeline."""
        if stage not in MANUAL_TRANSITION_STAGES:
            raise InvalidStageTransitionError(
                f"stage '{stage}' cannot be set manually; use the relevant action instead.")
        previous = opportunity.stage
        if previous == stage:
            return opportunity
        opportunity.stage = stage
        opportunity.updated_by = actor_user_id
        opportunity.updated_at = _now()
        opportunity = await self.opportunities.update(opportunity)
        await self._log(opportunity.tenant, opportunity.agent_id, "opportunity_stage_changed",
                        f"Stage changed from {previous} to {stage}.", tone="info",
                        opportunity_id=opportunity.id, actor_user_id=actor_user_id,
                        metadata={"from": previous, "to": stage})
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
    notifier: SalesNotificationService | None = None
    # Optional agent resolver (see OpportunityService.agents). When set, per-agent si_* config
    # drives manual create/requalify even without an explicit agent_config argument.
    agents: object | None = None

    def __post_init__(self) -> None:
        if self.opportunities is None:
            self.opportunities = InMemoryOpportunityStore()
        if self.activity_logs is None:
            self.activity_logs = InMemoryActivityLogStore()

    async def _resolve_scorer(self, tenant: str, agent_id: str,
                              agent_config: dict | None) -> QualificationService:
        if agent_config is None and self.agents is not None:
            agent = await self.agents.get(tenant, agent_id)
            agent_config = getattr(agent, "config", None) if agent is not None else None
        return self.qualification.with_config(agent_config)

    async def _log(self, tenant: str, agent_id: str, opportunity_id: str, action: str, detail: str, *,
                   tone: str = "info", actor_user_id: str | None = None, metadata: dict | None = None) -> None:
        await self.activity_logs.add(ActivityLog(
            id=_new_id(), tenant=tenant, agent_id=agent_id, opportunity_id=opportunity_id, action=action,
            detail=detail, tone=tone, actor_user_id=actor_user_id, metadata=metadata or {},
        ))

    async def create_manual(self, tenant: str, agent_id: str, payload: dict, actor_user_id: str | None = None,
                            run_qualification: bool = True, agent_config: dict | None = None) -> Opportunity:
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
            scorer = await self._resolve_scorer(tenant, agent_id, agent_config)
            qualification = scorer.qualify({
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
        # Notification trigger: a manually-created opportunity that needs human validation.
        if self.notifier is not None and opportunity.stage == "awaiting_review":
            await self.notifier.notify_review_required(opportunity)
        return opportunity

    async def assign_reviewer(self, opportunity: Opportunity, reviewer_user_id: str | None,
                              reviewer_name: str | None, actor_user_id: str | None = None) -> Opportunity:
        """Assign (or clear) a reviewer on an opportunity. Port of
        IdgSalesOpportunityMutationService::assignReviewer -- writes an audit-trail activity log
        (assigned/unassigned) and, when a reviewer is set, fires the reviewer-assigned notification."""
        previous_reviewer_id = opportunity.assigned_reviewer_user_id
        assigned = bool(reviewer_user_id) or bool(reviewer_name)
        opportunity.assigned_reviewer_user_id = reviewer_user_id
        opportunity.assigned_reviewer_name = reviewer_name
        opportunity.assigned_by_user_id = actor_user_id if assigned else None
        opportunity.assigned_at = _now() if assigned else None
        opportunity.updated_by = actor_user_id
        opportunity.updated_at = _now()
        opportunity = await self.opportunities.update(opportunity)

        label = reviewer_name or reviewer_user_id or ""
        await self._log(
            opportunity.tenant, opportunity.agent_id, opportunity.id,
            "opportunity_reviewer_assigned" if assigned else "opportunity_reviewer_unassigned",
            (f"Reviewer assigned on opportunity: {opportunity.title}" if assigned
             else f"Reviewer cleared on opportunity: {opportunity.title}"),
            tone="info", actor_user_id=actor_user_id,
            metadata={"previous_reviewer_user_id": previous_reviewer_id,
                      "assigned_reviewer_user_id": reviewer_user_id,
                      "assigned_reviewer_name": reviewer_name,
                      "assigned_by_user_id": opportunity.assigned_by_user_id,
                      "assigned_at": opportunity.assigned_at.isoformat() if opportunity.assigned_at else None,
                      "reviewer": label})

        if assigned and reviewer_user_id and self.notifier is not None:
            await self.notifier.notify_reviewer_assigned(opportunity, reviewer_user_id, actor_user_id)
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
                            requalify: bool = False, agent_config: dict | None = None) -> Opportunity:
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
            scorer = await self._resolve_scorer(opportunity.tenant, opportunity.agent_id, agent_config)
            qualification = scorer.qualify({
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
