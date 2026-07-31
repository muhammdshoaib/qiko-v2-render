"""Background scheduler sweeps for Sales Intelligence.

Port of the Laravel scheduler entries (idg-sales `bootstrap/app.php`):
 - `idg-sales:scan-sources`     (every N minutes) -> scan_due_sources
 - `idg-sales:notify-deadlines` (dailyAt 08:00)   -> send_deadline_reminders

These sweeps are store-agnostic: they take a fully-wired OpportunityService (in-memory in dev/
tests, Postgres-backed on the worker tier) and drive the SAME service methods the manual API
endpoints use, so scheduled and manual behaviour are identical. The arq cron wrappers that build a
worker-side DB session and invoke these live in app.tasks.worker.

Design notes:
 - Due-ness is derived from `last_scan_at` + the configured interval (not a stored `next_scan_at`),
   so the sweep is correct for any cadence and safe to run on a fixed (e.g. per-minute) cron.
 - Each per-source scan and per-opportunity reminder is wrapped so one failure never aborts the
   whole sweep. Genuine scan failures are already logged + notified inside `_scan_source`.
 - Deadline reminders dedupe on the `opportunity_deadline_reminded` activity-log row (written by
   `OpportunityService.record_deadline_reminder`) -- no extra schema/`deadline_reminded_at` column.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.deps import WorkerUnavailable, require_available_worker
from app.modules.sales_intelligence.models import (
    IngestionSource,
    Opportunity,
    cadence_to_minutes,
    merge_ingest_filter,
)
from app.modules.sales_intelligence.service import OpportunityService, SalesIntelligenceError

logger = logging.getLogger(__name__)

# source_key -> the OpportunityService scan method (reuses the manual-endpoint code path exactly).
_SCAN_METHODS = {"ungm": "scan_ungm", "ted": "scan_ted"}

# Stages past which a submission-deadline reminder is pointless (already pushed to CRM or rejected).
TERMINAL_STAGES = frozenset({"pushed", "rejected"})

# Activity-log action written per reminder; doubles as the "already reminded today" dedupe marker.
DEADLINE_REMINDER_ACTION = "opportunity_deadline_reminded"

# How many days out a deadline must be to trigger a reminder (matches the source's reminder window).
DEFAULT_DEADLINE_THRESHOLD_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Treat naive timestamps (e.g. SQLite round-trips) as UTC so comparisons never blow up."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _is_source_due(source: IngestionSource, *, interval_minutes: int, now: datetime) -> bool:
    """A source is due when it has never been scanned or its last scan is at least one cadence
    interval old. The interval comes from the source's own `scan_cadence` (falling back to the
    global `interval_minutes` for legacy cadences); a "manual" cadence is never auto-due.
    `last_scan_at` is stamped on both success and failure by `_scan_source`, so a failing source
    still backs off one interval rather than being retried every tick."""
    if not source.is_enabled():
        return False
    minutes = cadence_to_minutes(source.scan_cadence, default=interval_minutes)
    if minutes is None:  # manual cadence -> never auto-scanned
        return False
    if source.last_scan_at is None:
        return True
    return _as_utc(source.last_scan_at) + timedelta(minutes=max(1, minutes)) <= now


async def scan_due_sources(service: OpportunityService, *, now: datetime | None = None,
                           interval_minutes: int | None = None, agents=None, ingest_filters=None) -> dict:
    """Scan every ENABLED ingestion source (across all tenants/agents) whose cadence is due.

    Reuses `OpportunityService.scan_ungm`/`scan_ted`, so the existing notification triggers fire
    (new awaiting_review -> review-required; failure -> scan-failed). Returns a structured summary.

    `agents` (an AgentService/AgentStore with async get(tenant, agent_id)) is optional: when given
    (or set on `service.agents`), each source is scored with its own agent's si_* config; otherwise
    the scorer falls back to the IDG defaults, preserving existing behaviour."""
    now = now or _now()
    interval_minutes = interval_minutes if interval_minutes is not None else service.scan_interval_minutes
    agents = agents if agents is not None else getattr(service, "agents", None)
    ingest_filters = ingest_filters if ingest_filters is not None else getattr(service, "ingest_filters", None)

    sources = await service.sources.list_active()  # tenant=None -> all tenants
    scanned = skipped = failed = 0

    for source in sources:
        method_name = _SCAN_METHODS.get(source.source_key)
        if method_name is None or not _is_source_due(source, interval_minutes=interval_minutes, now=now):
            skipped += 1
            continue
        scan = getattr(service, method_name)
        try:
            if agents is None:
                raise WorkerUnavailable

            async def recheck() -> None:
                await require_available_worker(
                    agents=agents, tenant=source.tenant, agent_id=source.agent_id)

            agent = await require_available_worker(
                agents=agents, tenant=source.tenant, agent_id=source.agent_id)
            agent_config = getattr(agent, "config", None)
            # Apply the persisted per-agent ingest filter (saved keyword + allowlist bypasses) so
            # scheduled sweeps match the manual "scan now" and the saved config. No store -> {}.
            scan_filters: dict = {}
            if ingest_filters is not None:
                scan_filters = merge_ingest_filter({}, await ingest_filters.get_or_create(source.tenant, source.agent_id))
            await scan(
                source.tenant, source.agent_id, scan_filters, agent_config=agent_config,
                recheck_worker=recheck)
            scanned += 1
        except SalesIntelligenceError as exc:
            # Includes SourceInactiveError (source disabled mid-sweep) and re-raised scan failures --
            # both already logged/notified in-service. Keep sweeping the remaining sources.
            failed += 1
            logger.warning("sales scheduler: source scan failed",
                           extra={"tenant": source.tenant, "agent_id": source.agent_id,
                                  "source_key": source.source_key, "error": str(exc)})
        except Exception:  # noqa: BLE001 -- one bad source must never kill the whole sweep
            failed += 1
            logger.exception("sales scheduler: unexpected error scanning source",
                             extra={"tenant": source.tenant, "agent_id": source.agent_id,
                                    "source_key": source.source_key})

    summary = {"active_sources": len(sources), "scanned": scanned, "skipped": skipped, "failed": failed}
    logger.info("sales scheduler: scan sweep complete", extra=summary)
    return summary


def _due_in_days(opportunity: Opportunity, now: datetime) -> int:
    return (_as_utc(opportunity.deadline_at).date() - now.date()).days


async def _already_reminded_today(service: OpportunityService, opportunity: Opportunity,
                                  now: datetime) -> bool:
    logs = await service.activity_logs.list_for_agent(
        opportunity.tenant, opportunity.agent_id,
        opportunity_id=opportunity.id, action=DEADLINE_REMINDER_ACTION)
    return any(_as_utc(log.created_at).date() == now.date() for log in logs)


async def send_deadline_reminders(service: OpportunityService, *, now: datetime | None = None,
                                  threshold_days: int = DEFAULT_DEADLINE_THRESHOLD_DAYS,
                                  agents=None) -> dict:
    """Remind on every non-terminal opportunity whose deadline is within `threshold_days`.

    Idempotent: at most one reminder per opportunity per day, deduped on the
    `opportunity_deadline_reminded` activity log. Returns a structured summary."""
    now = now or _now()
    candidates = await service.opportunities.list_with_deadline()  # cross-tenant, live rows only
    considered = reminded = skipped = deduped = 0

    for opportunity in candidates:
        if opportunity.stage in TERMINAL_STAGES or opportunity.deadline_at is None:
            skipped += 1
            continue
        due = _due_in_days(opportunity, now)
        if not (0 <= due <= threshold_days):
            skipped += 1
            continue
        considered += 1
        try:
            if agents is None:
                raise WorkerUnavailable
            await require_available_worker(
                agents=agents, tenant=opportunity.tenant, agent_id=opportunity.agent_id)
            if await _already_reminded_today(service, opportunity, now):
                deduped += 1
                continue
            await require_available_worker(
                agents=agents, tenant=opportunity.tenant, agent_id=opportunity.agent_id)
            await service.record_deadline_reminder(opportunity, due)
            reminded += 1
        except Exception:  # noqa: BLE001 -- one bad opportunity must never kill the whole sweep
            logger.exception("sales scheduler: failed to send deadline reminder",
                             extra={"tenant": opportunity.tenant, "agent_id": opportunity.agent_id,
                                    "opportunity_id": opportunity.id})

    summary = {"with_deadline": len(candidates), "considered": considered,
               "reminded": reminded, "deduped": deduped, "skipped": skipped}
    logger.info("sales scheduler: deadline-reminder sweep complete", extra=summary)
    return summary
