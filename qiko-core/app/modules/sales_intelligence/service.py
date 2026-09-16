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
from datetime import datetime, timedelta, timezone

from app.modules.sales_intelligence import source_catalog
from app.modules.sales_intelligence.connectors import (
    GenericHttpNoticeConnector,
    TedNoticeConnector,
    UngmNoticeConnector,
)
from app.modules.sales_intelligence.models import (
    ActivityLog,
    ActivityLogStore,
    EDITABLE_OPPORTUNITY_FIELDS,
    IngestionSource,
    IngestionSourceStore,
    InMemoryActivityLogStore,
    InMemoryIngestionSourceStore,
    InMemoryOpportunityStore,
    MANUAL_DETAIL_FIELDS,
    MANUAL_TRANSITION_STAGES,
    Opportunity,
    OpportunityStore,
    SCAN_CADENCES,
    SOURCE_STATUSES,
)
from app.core.deps import WorkerUnavailable
from app.modules.sales_intelligence.notifications import SalesNotificationService
from app.modules.sales_intelligence.orchestration import build_facets
from app.modules.sales_intelligence.qualification import QualificationService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


_EMPTY_VALUES = (None, "", [], {})


def _extract_manual_fields(payload: dict) -> dict:
    """Pull the enriched, column-less manual fields (MANUAL_DETAIL_FIELDS) out of a create/update
    payload, dropping empty values and pruning blank contact/link rows. The result is stored under
    Opportunity.raw_payload["manual"] and surfaced by OpportunityDetailService."""
    manual: dict = {}
    for key in MANUAL_DETAIL_FIELDS:
        if key not in payload:
            continue
        value = payload[key]
        if value in _EMPTY_VALUES:
            continue
        if key in ("contacts", "links") and isinstance(value, list):
            cleaned = [v for v in value
                       if isinstance(v, dict) and any(x not in (None, "") for x in v.values())]
            if not cleaned:
                continue
            manual[key] = cleaned
        else:
            manual[key] = value
    return manual


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
    generic: GenericHttpNoticeConnector = field(default_factory=GenericHttpNoticeConnector)
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
    # Wired from app.state in main.py once both exist (see the late attribute assignments there,
    # mirroring app.state.cost_guard.notifications). When task_queue is None (every existing call
    # site that does not pass it, and most tests), the enqueue gate in _scan_source() is a no-op --
    # a service built the old way behaves exactly as before.
    task_queue: object | None = None
    pipeline_run_store: object | None = None
    # Optional ai.caps.CostGuard. When wired, _scan_source() skips (never raises) enqueueing the
    # agentic pipeline once the tenant/agent's monthly cap is reached -- the same guard the chat
    # path (Worker.answer) already enforces, applied here too (QIW cost incident, 2026-09-14).
    cost_guard: object | None = None
    # Minimum time between two pipeline enqueues for the SAME opportunity. Without this, an
    # opportunity that stays awaiting_review across re-scans got a fresh Synthesizer/Critic
    # (Sonnet 4.5) run on every single scan cycle, unbounded (QIW cost incident, 2026-09-14).
    pipeline_reenqueue_cooldown_minutes: int = 60
    # Total pipeline enqueues a single opportunity may ever accrue. The cooldown above only
    # bounds the RATE, not the total: an opportunity that never resolves (stays awaiting_review
    # forever) still got a fresh run every time the cooldown elapsed, unbounded, so spend kept
    # climbing even with the cooldown in place (QIW cost incident continuation, 2026-09-16). None
    # means unlimited.
    pipeline_max_attempts: int | None = 3

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

    async def attach_source(self, tenant: str, agent_id: str, source_key: str, name: str | None = None,
                            config_input: dict | None = None, actor_user_id: str | None = None) -> IngestionSource:
        """Attach a first-party catalog portal (ted/ungm) or a custom source to the agent. Idempotent:
        re-attaching returns the existing source. Custom sources (not in the catalog) require a display
        name and a config.url, and use the `generic` connector (config.scannable=True, scanned via
        the SSRF-guarded GenericHttpNoticeConnector), mirroring Staging's catalog `scannable` flag."""
        definition = source_catalog.definition(source_key)
        if definition is None:
            display_name = (name or "").strip()
            if not display_name:
                raise SalesIntelligenceError("name is required when adding a custom source (not in the built-in catalog).")
            config = dict(config_input or {})
            if not str(config.get("url") or "").strip():
                raise SalesIntelligenceError("config.url is required for a custom source.")
            connector, auth_status, source_type, scannable = "generic", None, "portal", True
        else:
            display_name = (name or "").strip() or definition["name"]
            config = {**(definition.get("config") or {}), **(config_input or {})}
            connector = definition["connector"]
            auth_status = definition["auth_status"]
            source_type = definition["type"]
            scannable = bool(definition["scannable"])
        config["connector"] = connector
        config["scannable"] = scannable
        source = await self.sources.get_or_create(tenant, agent_id, source_key, {
            "name": display_name, "type": source_type, "status": "inactive", "auth_status": auth_status,
            "scan_cadence": _default_source_cadence(self.scan_interval_minutes), "config": config,
        })
        await self._log(tenant, agent_id, "source_added", f"{display_name} added to this agent.",
                        tone="success", actor_user_id=actor_user_id,
                        metadata={"source_key": source_key, "connector": connector, "custom": definition is None})
        return source

    async def detach_source(self, tenant: str, agent_id: str, source_key: str,
                            actor_user_id: str | None = None) -> None:
        """Remove an attached source from the agent. Opportunities keep their source_key (plain string,
        no FK), so no rows are orphaned; re-attaching from the catalog recreates the source."""
        source = await self.sources.get(tenant, agent_id, source_key)
        if source is None:
            raise OpportunityNotFoundError(f"source not attached: {source_key}")
        await self.sources.delete(tenant, agent_id, source_key)
        await self._log(tenant, agent_id, "source_removed", f"{source.name} removed from this agent.",
                        tone="info", actor_user_id=actor_user_id, metadata={"source_key": source_key})

    async def update_source_status(self, tenant: str, agent_id: str, source_key: str, status: str,
                                   actor_user_id: str | None = None) -> IngestionSource:
        if status not in SOURCE_STATUSES:
            raise SalesIntelligenceError(f"invalid status: {status}")
        # A first-party catalog key (ted/ungm) is seeded on demand; any other key must already be an
        # attached (custom) source, otherwise it is unknown.
        if source_catalog.is_valid_key(source_key):
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
        if cadence not in SCAN_CADENCES:
            raise SalesIntelligenceError(f"invalid scan_cadence: {cadence}")
        if source_catalog.is_valid_key(source_key):
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
                        agent_config: dict | None = None, recheck_worker=None) -> dict:
        return await self._scan_source(
            tenant, agent_id, "ungm", "UNGM Public Notices",
            lambda: self.ungm.search(filters), actor_user_id, agent_config, recheck_worker)

    async def scan_ted(self, tenant: str, agent_id: str, filters: dict, actor_user_id: str | None = None,
                       agent_config: dict | None = None, recheck_worker=None) -> dict:
        return await self._scan_source(
            tenant, agent_id, "ted", "TED - EU Tenders",
            lambda: self.ted.search(filters), actor_user_id, agent_config, recheck_worker)

    async def scan_source(self, tenant: str, agent_id: str, source_key: str, filters: dict,
                          actor_user_id: str | None = None, agent_config: dict | None = None,
                          recheck_worker=None) -> dict:
        """Scan any attached source, dispatching to the connector for its key: the built-in ted/ungm
        connectors, or the generic HTTP connector for a custom source (config.connector == generic)."""
        if source_key == "ted":
            return await self.scan_ted(tenant, agent_id, filters, actor_user_id, agent_config, recheck_worker)
        if source_key == "ungm":
            return await self.scan_ungm(tenant, agent_id, filters, actor_user_id, agent_config, recheck_worker)
        source = await self.sources.get(tenant, agent_id, source_key)
        if source is None:
            raise OpportunityNotFoundError(f"source not attached: {source_key}")
        connector = str((source.config or {}).get("connector") or source_catalog.connector_key(source_key))
        if connector != "generic":
            raise SourceInactiveError(f"{source_key} is not scannable.")
        cfg = source.config or {}
        return await self._scan_source(
            tenant, agent_id, source_key, source.name,
            lambda: self.generic.search(filters, cfg), actor_user_id, agent_config, recheck_worker)

    async def _resolve_scorer(self, tenant: str, agent_id: str,
                              agent_config: dict | None) -> QualificationService:
        """Build the per-agent qualification scorer. Uses an explicitly-passed agent_config (from
        the manual API path) or, failing that, resolves the agent via the optional `agents` store
        (scheduler/background path). Falls back to the default IDG scorer when neither is available."""
        if agent_config is None and self.agents is not None:
            agent = await self.agents.get(tenant, agent_id)
            agent_config = getattr(agent, "config", None) if agent is not None else None
        return self.qualification.with_config(agent_config)

    async def _may_enqueue_pipeline(self, tenant: str, agent_id: str, opportunity: Opportunity) -> bool:
        """The full cost-control gate for the agentic pipeline, checked right before an enqueue
        that _scan_source() would otherwise make unconditionally on every scan cycle.

        Cooldown first (cheap, no I/O): an opportunity that already got a pipeline run enqueued
        recently -- whether it is still in flight or just finished and is still awaiting_review --
        does not get another one until pipeline_reenqueue_cooldown_minutes has passed. Then the
        total-attempts cap (also cheap, no I/O): the cooldown only bounds the rate for one
        opportunity, not how many times it can ever run, so an opportunity that never resolves
        would otherwise accrue an unbounded number of runs, one per cooldown window, forever.
        Then the cost cap (one cached DB-backed read via CostGuard): even a correctly-capped
        pipeline can still exceed a tenant's configured monthly AI spend if enough opportunities
        are ambiguous at once, so this is a third, independent backstop, not a substitute for
        either of the above.
        """
        last = opportunity.pipeline_last_enqueued_at
        if last is not None:
            cooldown = timedelta(minutes=self.pipeline_reenqueue_cooldown_minutes)
            if _now() - last < cooldown:
                return False
        if (self.pipeline_max_attempts is not None
                and opportunity.pipeline_attempt_count >= self.pipeline_max_attempts):
            return False
        if self.cost_guard is not None:
            decision = await self.cost_guard.check(tenant, agent_id)
            if not decision.allowed:
                return False
        return True

    async def _scan_source(self, tenant: str, agent_id: str, source_key: str, source_name: str,
                           search_fn, actor_user_id: str | None = None,
                           agent_config: dict | None = None, recheck_worker=None) -> dict:
        import asyncio

        async def recheck() -> None:
            if recheck_worker is not None:
                await recheck_worker()

        await recheck()
        if source_key == "ted":
            source = await self.ensure_ted_source(tenant, agent_id)
        elif source_key == "ungm":
            source = await self.ensure_ungm_source(tenant, agent_id)
        else:
            source = await self.sources.get(tenant, agent_id, source_key)
            if source is None:
                raise OpportunityNotFoundError(f"source not attached: {source_key}")
        self.assert_source_active(source)
        source.last_scan_status = "running"
        source.last_error = None
        await recheck()
        await self.sources.update(source)

        scorer = await self._resolve_scorer(tenant, agent_id, agent_config)

        try:
            result = await asyncio.to_thread(search_fn)
            await recheck()
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

                await recheck()
                opportunity = await (self.opportunities.add(opportunity) if is_new else self.opportunities.update(opportunity))
                created += 1 if is_new else 0
                updated += 0 if is_new else 1
                upserted.append(opportunity)

                await recheck()
                await self._log(tenant, agent_id, "opportunity_ingested" if is_new else "opportunity_updated",
                                f"{'Ingested' if is_new else 'Updated'} {source_key.upper()} opportunity: {opportunity.title}",
                                tone="success", opportunity_id=opportunity.id, actor_user_id=actor_user_id,
                                metadata={"source_key": source_key, "external_id": external_id,
                                         "recommendation": opportunity.recommendation})

                # Notification trigger: a freshly-ingested opportunity that needs human validation.
                if is_new and self.notifier is not None and opportunity.stage == "awaiting_review":
                    await recheck()
                    await self.notifier.notify_review_required(opportunity)

                # Cost-control gate: route only the ambiguous middle to the agentic pipeline. This
                # is NOT gated on `is_new` like the notification above -- a notice that stayed
                # "awaiting_review" across a re-scan deserves the same resolution attempt every
                # time, not just on first ingest. build_facets() reflects this scan's own
                # qualify() output (missing_fields/risks); a confident "Bid"/"No Bid" notice never
                # has either, so it never reaches here regardless of the task_queue check below.
                if self.task_queue is not None and opportunity.stage == "awaiting_review":
                    facets = build_facets({
                        "missing_fields": qualification.get("missing_fields", []),
                        "risks": qualification.get("risks", []),
                    })
                    if facets and await self._may_enqueue_pipeline(tenant, agent_id, opportunity):
                        from app.modules.agentcore.orchestration import Pipeline, PipelineConfig

                        pipeline_config = PipelineConfig(
                            tenant=tenant, agent_id=agent_id, subject=opportunity.title,
                            facets=facets, kind="idg_qualification")
                        pipeline_run = Pipeline.new_run(pipeline_config)
                        await self.pipeline_run_store.add(pipeline_run)
                        opportunity.pipeline_last_enqueued_at = _now()
                        opportunity.pipeline_attempt_count += 1
                        await self.opportunities.update(opportunity)
                        await self.task_queue.enqueue(
                            "run_idg_qualification_pipeline", tenant=tenant, agent_id=agent_id,
                            opportunity_id=opportunity.id, run_id=pipeline_run.run_id)

            source.last_scan_status = "success"
            source.last_scan_at = _now()
            source.opportunities_found = len(upserted)
            source.last_error = None
            await recheck()
            source = await self.sources.update(source)

            await recheck()
            await self._log(tenant, agent_id, f"{source_key}_scan_completed",
                            f"{source_key.upper()} scan completed with {len(upserted)} opportunities."
                            + (f" {skipped} notices skipped by ingest filters." if skipped else ""),
                            tone="success", actor_user_id=actor_user_id,
                            metadata={"source_key": source_key, "created": created, "updated": updated,
                                     "skipped": skipped, "payload": result.get("payload", {}),
                                     "total_notice_count": result.get("total_notice_count")})

            await recheck()
            return {"source": source, "opportunities": upserted, "created": created, "updated": updated, "skipped": skipped}
        except (SourceInactiveError, WorkerUnavailable):
            raise
        except Exception as e:
            await recheck()
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

        # Enriched, column-less manual fields (reference/summaries/requirements/...) are kept in the
        # raw_payload JSON blob so they persist + round-trip without a schema migration.
        manual = _extract_manual_fields(payload)
        if manual:
            opportunity.raw_payload["manual"] = manual
        # Qualification columns the operator set by hand. When run_qualification is on these get
        # overwritten by the scorer below; otherwise the manual values are kept.
        if payload.get("recommendation") is not None:
            opportunity.recommendation = payload["recommendation"]
        if payload.get("qualification_score") is not None:
            opportunity.qualification_score = payload["qualification_score"]
        if payload.get("confidence") is not None:
            opportunity.confidence = payload["confidence"]
        # Ali collects free-text notes on the create form; V2 stores them as the human-review notes.
        if payload.get("notes"):
            opportunity.human_review_notes = payload["notes"]

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

        # Enriched, column-less manual fields live in raw_payload["manual"]; merge in the supplied
        # ones (empty values clear the field) and track them in the same change set as columns.
        current_manual = dict((opportunity.raw_payload or {}).get("manual") or {})
        incoming_manual = {k: payload[k] for k in MANUAL_DETAIL_FIELDS if k in payload}
        if incoming_manual:
            cleaned = _extract_manual_fields(payload)
            for key in incoming_manual:
                old_value = current_manual.get(key)
                new_value = cleaned.get(key)  # absent -> cleared
                if old_value == new_value:
                    continue
                changes[key] = {"from": self._serialize(old_value), "to": self._serialize(new_value)}
                if new_value is None:
                    current_manual.pop(key, None)
                else:
                    current_manual[key] = new_value
            raw = dict(opportunity.raw_payload or {})
            if current_manual:
                raw["manual"] = current_manual
            else:
                raw.pop("manual", None)
            opportunity.raw_payload = raw

        # Ali's edit form keeps free-text notes; V2 maps them onto the human-review notes column.
        if "notes" in payload:
            new_notes = payload["notes"] or None
            if new_notes != opportunity.human_review_notes:
                changes["notes"] = {"from": opportunity.human_review_notes, "to": new_notes}
                opportunity.human_review_notes = new_notes

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
