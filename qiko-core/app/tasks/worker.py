"""arq worker entrypoint. Run with: `arq app.tasks.worker.WorkerSettings`.

Each registered job is wrapped to arq's (ctx, **kwargs) calling convention. A DB sessionmaker is
built once at worker startup and kept on the arq context, so jobs share one engine.

Sales-Intelligence has two scheduled sweeps (cron_jobs), the arq analogue of the idg-sales Laravel
scheduler: scan enabled ingestion sources on cadence, and send deadline reminders once a day.
"""
from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.modules.sales_intelligence import scheduler as sales_scheduler
from app.tasks import jobs


async def ingest_document(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    return await jobs.ingest_document(**kwargs)


async def send_email(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    return await jobs.send_email(**kwargs)


async def generate_tender_artifacts(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    # Build the RFP stores from the worker's shared sessionmaker; the enqueue only carries the
    # serializable ids (tenant/pack_id/agent_id).
    return await jobs.generate_tender_artifacts(sessionmaker=ctx["sessionmaker"], **kwargs)


async def generate_slack_digest(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    return await jobs.generate_slack_digest(sessionmaker=ctx["sessionmaker"], **kwargs)


def _build_sales_runtime(sessionmaker):
    """Build a Postgres-backed OpportunityService for a worker sweep, mirroring the DB-store wiring
    in app.main's lifespan so scheduled scans read/write the same source of truth as the API."""
    from app.db.stores import (
        SqlActivityLogStore,
        SqlAgentStore,
        SqlIngestFilterSettingStore,
        SqlIngestionSourceStore,
        SqlNotificationStore,
        SqlOpportunityStore,
    )
    from app.modules.agents.service import AgentService
    from app.modules.notifications.service import NotificationService
    from app.modules.sales_intelligence.notifications import SalesNotificationService
    from app.modules.sales_intelligence.service import OpportunityService

    notifier = SalesNotificationService(notifications=NotificationService(store=SqlNotificationStore(sessionmaker)))
    agents = AgentService(store=SqlAgentStore(sessionmaker))
    service = OpportunityService(
        scan_interval_minutes=get_settings().idg_sales_scan_interval_minutes,
        sources=SqlIngestionSourceStore(sessionmaker),
        opportunities=SqlOpportunityStore(sessionmaker),
        activity_logs=SqlActivityLogStore(sessionmaker),
        notifier=notifier,
        agents=agents,
    )
    ingest_filters = SqlIngestFilterSettingStore(sessionmaker)
    return service, agents, ingest_filters


async def scan_due_sources(ctx):  # pragma: no cover - invoked by the arq cron runtime
    service, agents, ingest_filters = _build_sales_runtime(ctx["sessionmaker"])
    return await sales_scheduler.scan_due_sources(service, agents=agents, ingest_filters=ingest_filters)


async def purge_expired_signups(ctx):  # pragma: no cover - invoked by the arq cron runtime
    from app.db.stores import SqlPendingSignupStore
    return {"purged": await SqlPendingSignupStore(ctx["sessionmaker"]).purge_expired()}


async def send_deadline_reminders(ctx):  # pragma: no cover - invoked by the arq cron runtime
    service, agents, _ingest_filters = _build_sales_runtime(ctx["sessionmaker"])
    return await sales_scheduler.send_deadline_reminders(service, agents=agents)


async def erase_audit_subject(ctx: dict, **kwargs) -> int:  # pragma: no cover - worker runtime
    from app.db.stores import SqlAuditStore

    # The maintenance connection, which is the only one that can UPDATE audit_events once the boundary
    # is in force. Nothing in the API process has it any more.
    return await jobs.erase_audit_subject(
        store=SqlAuditStore(ctx.get("audit_sessionmaker") or ctx["sessionmaker"]), **kwargs)


FUNCTIONS = [ingest_document, send_email, generate_tender_artifacts, erase_audit_subject,
             generate_slack_digest]

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


CRON_JOBS = [
    # every minute, gated by per-source due-ness
    cron(scan_due_sources, name="sales_intel:scan_due_sources", second=0, unique=True),
    # dailyAt 08:00 (idg-sales notify-deadlines parity)
    cron(send_deadline_reminders, name="sales_intel:send_deadline_reminders", hour=8, minute=0, unique=True),
    cron(purge_expired_signups, name="identity:purge_expired_signups", hour=2, minute=15, unique=True),
    # Daily, off-peak. Nothing enforced the retention the model docstring claimed, so the trail grew
    # personal data indefinitely while asserting that it did not.
    cron(apply_audit_retention, name="audit:apply_retention", hour=3, minute=30, unique=True),
    # Before retention, and on the previous day, so a day is archived while it is still in the hot tier.
    # Exporting after the delete would lose exactly the rows the archive exists to keep.
    cron(export_audit_archive, name="audit:export_archive", hour=3, minute=0, unique=True),
]


async def on_startup(ctx) -> None:  # pragma: no cover - worker runtime
    from app.core.config import get_settings
    from app.core.db import build_engine, build_sessionmaker

    engine = build_engine()
    ctx["engine"] = engine
    ctx["sessionmaker"] = build_sessionmaker(engine)

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
