"""arq worker entrypoint. Run with: `arq app.tasks.worker.WorkerSettings`.

Each registered job is wrapped to arq's (ctx, **kwargs) calling convention. A DB sessionmaker is
built once at worker startup and kept on the arq context, so jobs share one engine.

Sales-Intelligence has two scheduled sweeps (cron_jobs), the arq analogue of the idg-sales Laravel
scheduler: scan enabled ingestion sources on cadence, and send deadline reminders once a day.
"""
from __future__ import annotations

import asyncio

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.modules.billing.reconciliation import InvoiceReconciliationService
from app.modules.sales_intelligence import scheduler as sales_scheduler
from app.tasks import jobs


async def ingest_document(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    return await jobs.ingest_document(**kwargs)


async def process_uploaded_document(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    return await jobs.process_uploaded_document(sessionmaker=ctx.get("sessionmaker"), **kwargs)


async def send_email(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    return await jobs.send_email(**kwargs)


async def generate_tender_artifacts(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    # Build the RFP stores from the worker's shared sessionmaker; the enqueue only carries the
    # serializable ids (tenant/pack_id/agent_id).
    return await jobs.generate_tender_artifacts(sessionmaker=ctx["sessionmaker"], **kwargs)


async def run_intelligence_pipeline(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    # Build the Pipeline from the worker's own DB connection; the API only puts tenant/agent_id/run_id
    # on Redis so the run record and model state stay consistent.
    return await jobs.run_intelligence_pipeline(sessionmaker=ctx["sessionmaker"], **kwargs)


async def run_idg_qualification_pipeline(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    # Same reasoning as run_intelligence_pipeline above: only serialisable ids reach Redis
    # (tenant/agent_id/opportunity_id/run_id), and the Pipeline (with its IdgScout adapter bound to
    # the fetched Opportunity) is rebuilt here from the worker's own DB connection.
    return await jobs.run_idg_qualification_pipeline(sessionmaker=ctx["sessionmaker"], **kwargs)


async def generate_slack_digest(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    # The SYNC sessionmaker is what carries the Slack installation store (see sync_stores.py):
    # without it the job cannot resolve a bot token and could never post the digest it paid for.
    return await jobs.generate_slack_digest(
        sessionmaker=ctx["sessionmaker"], sync_sessionmaker=ctx.get("sync_sessionmaker"), **kwargs)


def _build_sales_runtime(sessionmaker, redis=None):
    """Build a Postgres-backed OpportunityService for a worker sweep, mirroring the DB-store wiring
    in app.main's lifespan so scheduled scans read/write the same source of truth as the API.

    `redis` is the arq worker's own connection pool (ctx["redis"], set by arq itself before any
    job or cron function ever runs -- see arq.worker.Worker.main). Wiring it as task_queue lets
    this cron sweep enqueue run_idg_qualification_pipeline for a "Review" notice the same way
    app.main's durable (use_db_stores) branch wires task_queue/pipeline_run_store for the
    manually-triggered API scan. Unlike that main.py wiring, there is no EagerTaskQueue concern to
    guard against here: this module is the arq worker process's own entrypoint, so it only ever
    runs when TASK_BACKEND=arq is the actual configured backend.

    Reusing ctx["redis"] (rather than building a fresh ArqTaskQueue with its own pool) matters
    because scan_due_sources ticks once a minute: opening a brand-new Redis connection on every
    tick would leak connections, where ArqTaskQueue only opens a pool when its own _pool is unset.
    """
    from app.db.stores import (
        SqlActivityLogStore,
        SqlAgentStore,
        SqlCostCapStore,
        SqlIngestFilterSettingStore,
        SqlIngestionSourceStore,
        SqlNotificationStore,
        SqlOpportunityStore,
        SqlPipelineRunStore,
        SqlUsageStore,
    )
    from app.modules.agents.service import AgentService
    from app.modules.ai.caps import CostGuard
    from app.modules.notifications.service import NotificationService
    from app.modules.sales_intelligence.notifications import SalesNotificationService
    from app.modules.sales_intelligence.service import OpportunityService
    from app.tasks.queue import ArqTaskQueue

    notifications = NotificationService(store=SqlNotificationStore(sessionmaker))
    notifier = SalesNotificationService(notifications=notifications)
    agents = AgentService(store=SqlAgentStore(sessionmaker))
    task_queue = ArqTaskQueue(redis_url=get_settings().redis_url, _pool=redis) if redis is not None else None
    # No CostGuard existed on this cron path before (QIW cost incident, 2026-09-14): the arq
    # worker process never built one, so the scheduled scan sweep could never be capped, mirroring
    # app.main's own CostGuard(caps=..., usage=...) + notifications wiring.
    cost_guard = CostGuard(caps=SqlCostCapStore(sessionmaker), usage=SqlUsageStore(sessionmaker))
    cost_guard.notifications = notifications
    service = OpportunityService(
        scan_interval_minutes=get_settings().idg_sales_scan_interval_minutes,
        pipeline_reenqueue_cooldown_minutes=get_settings().idg_pipeline_reenqueue_cooldown_minutes,
        pipeline_max_attempts=get_settings().idg_pipeline_max_attempts,
        sources=SqlIngestionSourceStore(sessionmaker),
        opportunities=SqlOpportunityStore(sessionmaker),
        activity_logs=SqlActivityLogStore(sessionmaker),
        notifier=notifier,
        agents=agents,
        task_queue=task_queue,
        pipeline_run_store=SqlPipelineRunStore(sessionmaker),
        cost_guard=cost_guard,
    )
    ingest_filters = SqlIngestFilterSettingStore(sessionmaker)
    return service, agents, ingest_filters


async def scan_due_sources(ctx):  # pragma: no cover - invoked by the arq cron runtime
    service, agents, ingest_filters = _build_sales_runtime(ctx["sessionmaker"], redis=ctx.get("redis"))
    return await sales_scheduler.scan_due_sources(service, agents=agents, ingest_filters=ingest_filters)


async def purge_expired_signups(ctx):  # pragma: no cover - invoked by the arq cron runtime
    from app.db.stores import SqlPendingSignupStore
    return {"purged": await SqlPendingSignupStore(ctx["sessionmaker"]).purge_expired()}


async def send_deadline_reminders(ctx):  # pragma: no cover - invoked by the arq cron runtime
    service, agents, _ingest_filters = _build_sales_runtime(ctx["sessionmaker"], redis=ctx.get("redis"))
    return await sales_scheduler.send_deadline_reminders(service, agents=agents)


async def sync_intelligence_signals(ctx):  # pragma: no cover - invoked by the arq cron runtime
    # Reuses the exact same catalog/knowledge wiring as app.main's own lifespan (durable branch):
    # _build_intelligence_catalog() and KnowledgeService(store=SqlVectorStore(...)) so the cron
    # sweep refreshes GitHub/Qiko Track signals through the same source of truth the API uses.
    from app.db.stores import SqlAgentStore, SqlSignalStore, SqlVectorStore
    from app.main import _build_intelligence_catalog
    from app.modules.agents.service import AgentService
    from app.modules.intelligence.scheduler import sync_stale_signals
    from app.modules.knowledge.service import KnowledgeService

    sessionmaker = ctx["sessionmaker"]
    catalog = _build_intelligence_catalog()
    agents = AgentService(store=SqlAgentStore(sessionmaker))
    signal_store = SqlSignalStore(sessionmaker)
    knowledge = KnowledgeService(store=SqlVectorStore(sessionmaker))
    return await sync_stale_signals(catalog, signal_store, agents=agents, knowledge=knowledge)


async def erase_audit_subject(ctx: dict, **kwargs) -> int:  # pragma: no cover - worker runtime
    from app.db.stores import SqlAuditStore

    # The maintenance connection, which is the only one that can UPDATE audit_events once the boundary
    # is in force. Nothing in the API process has it any more.
    return await jobs.erase_audit_subject(
        store=SqlAuditStore(ctx.get("audit_sessionmaker") or ctx["sessionmaker"]), **kwargs)


async def reconcile_invoices(ctx) -> dict:  # pragma: no cover - invoked by the arq cron runtime
    from app.db.sync_stores import SqlInvoiceStore
    from app.integrations.clients import StripeClient

    svc = InvoiceReconciliationService(
        invoices=SqlInvoiceStore(ctx["sync_sessionmaker"]),
        gateway=StripeClient())
    return await asyncio.to_thread(svc.reconcile)


async def draft_jm_intent_signals(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    # Only tenant and investor_ref reach Redis; the activity and signal stores are rebuilt here
    # from the worker's own DB connection, like every other job in this tier.
    return await jobs.draft_jm_intent_signals(sessionmaker=ctx["sessionmaker"], **kwargs)


FUNCTIONS = [ingest_document, process_uploaded_document, send_email, generate_tender_artifacts,
             erase_audit_subject, generate_slack_digest, reconcile_invoices, run_intelligence_pipeline,
             run_idg_qualification_pipeline, draft_jm_intent_signals]

# arq cron is calendar-based (no native "every N minutes" interval). Rather than encode the
# configured cadence into a minute-set at startup, the scan cron ticks once a minute and the sweep
# gates each source on its own due-ness (last_scan_at + interval), so it stays correct for ANY
# idg_sales_scan_interval_minutes. `unique=True` (arq default) means a single tick runs even with
# multiple worker replicas, so scans never double-run.
async def export_audit_archive(ctx: dict) -> dict:
    from app.db.stores import SqlAuditArchiveStore, SqlAuditStore
    from app.modules.storage.backend import get_storage_backend

    # The digest ledger is written by this job, so it uses the maintenance connection too.
    sm = ctx.get("audit_sessionmaker") or ctx["sessionmaker"]
    return await jobs.export_audit_archive(
        SqlAuditStore(ctx["sessionmaker"]), SqlAuditArchiveStore(sm), get_storage_backend())


async def apply_audit_retention(ctx: dict) -> dict:
    from app.db.stores import SqlAuditStore

    # Retention deletes and updates audit_events, which the application role must not be able to do.
    return await jobs.apply_audit_retention(
        SqlAuditStore(ctx.get("audit_sessionmaker") or ctx["sessionmaker"]))


async def purge_slack_messages(ctx: dict) -> dict:  # pragma: no cover - arq cron runtime
    from app.db.stores import SqlSlackChannelStore

    return await jobs.purge_slack_messages(
        SqlSlackChannelStore(ctx["sessionmaker"]),
        retention_days=get_settings().slack_message_retention_days)


CRON_JOBS = [
    # every minute, gated by per-source due-ness
    cron(scan_due_sources, name="sales_intel:scan_due_sources", second=0, unique=True),
    # dailyAt 08:00 (idg-sales notify-deadlines parity)
    cron(send_deadline_reminders, name="sales_intel:send_deadline_reminders", hour=8, minute=0, unique=True),
    # every 15 minutes, gated by sync_stale_signals's own per-source due-ness (default 60-minute
    # interval) -- same tick-often-let-due-ness-decide relationship scan_due_sources has above.
    cron(sync_intelligence_signals, name="intelligence:sync_stale_signals",
         minute=set(range(0, 60, 15)), unique=True),
    cron(purge_expired_signups, name="identity:purge_expired_signups", hour=2, minute=15, unique=True),
    # Daily, off-peak. Nothing enforced the retention the model docstring claimed, so the trail grew
    # personal data indefinitely while asserting that it did not.
    cron(apply_audit_retention, name="audit:apply_retention", hour=3, minute=30, unique=True),
    # Before retention, and on the previous day, so a day is archived while it is still in the hot tier.
    # Exporting after the delete would lose exactly the rows the archive exists to keep.
    cron(export_audit_archive, name="audit:export_archive", hour=3, minute=0, unique=True),
    # Captured Slack message text is third-party personal data, and a channel whose digest never
    # posts would otherwise keep it forever. Off-peak, once a day.
    cron(purge_slack_messages, name="channels:purge_slack_messages", hour=4, minute=0, unique=True),
    # Sync open invoices plus the last 24h of new invoices from Stripe so the console never drifts
    # from the source of truth between webhook deliveries and retries.
    cron(reconcile_invoices, name="billing:reconcile_invoices", hour=3, minute=0, unique=True),
]


async def on_startup(ctx) -> None:  # pragma: no cover - worker runtime
    from app.core.config import get_settings
    from app.core.db import build_engine, build_sessionmaker, build_sync_engine, build_sync_sessionmaker

    engine = build_engine()
    ctx["engine"] = engine
    ctx["sessionmaker"] = build_sessionmaker(engine)

    # A synchronous engine as well, because two durable stores the jobs need are synchronous by
    # design (the billing stores and the Slack installation store -- see app/db/sync_stores.py).
    sync_engine = build_sync_engine()
    ctx["sync_engine"] = sync_engine
    ctx["sync_sessionmaker"] = build_sync_sessionmaker(sync_engine)

    # A separate engine for the audit maintenance role, when one is configured. Retention and erasure
    # need UPDATE and DELETE on audit_events, which migration 0039 takes away from the application role,
    # so those two jobs use this connection and nothing else does.
    #
    # Falls back to the ordinary sessionmaker when unset, so the migration and this wiring can ship in
    # either order without a window where retention silently stops.
    maint_url = get_settings().audit_maint_database_url
    if maint_url:
        maint_engine = build_engine(maint_url)
        ctx["audit_maint_engine"] = maint_engine
        ctx["audit_sessionmaker"] = build_sessionmaker(maint_engine)
    else:
        ctx["audit_sessionmaker"] = ctx["sessionmaker"]


async def on_shutdown(ctx) -> None:  # pragma: no cover - worker runtime
    for key in ("engine", "audit_maint_engine"):
        engine = ctx.get(key)
        if engine is not None:
            await engine.dispose()
    sync_engine = ctx.get("sync_engine")
    if sync_engine is not None:
        sync_engine.dispose()


class WorkerSettings:
    """arq worker configuration (worker-default; ingest/voice queues use the same functions)."""

    functions = FUNCTIONS
    cron_jobs = CRON_JOBS
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Retry a killed/failed job (e.g. generate_tender_artifacts interrupted by a deploy) instead of
    # leaving it stuck. Its drafts stage is resumable/idempotent (skips already-drafted questions),
    # so a retry re-enters the loop and finishes the not-yet-drafted work without duplicating any.
    max_tries = 3
    # The full generate_tender_artifacts pipeline (extract -> sections -> brief -> compliance ->
    # per-section drafts) far exceeds arq's 300s default for a real tender (dozens of grounded LLM
    # calls). Give it 30 minutes so a whole tender drafts in one run instead of timing out mid-way
    # and thrashing on retries. Individual LLM calls keep their own read timeouts.
    job_timeout = 1800
