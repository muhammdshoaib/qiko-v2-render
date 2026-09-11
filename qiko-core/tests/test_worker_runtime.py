from datetime import datetime, timedelta, timezone

from app.tasks.jobs import registry
from app.tasks.queue import ArqTaskQueue, EagerTaskQueue, get_task_queue
from app.tasks.worker import WorkerSettings


def test_worker_settings_registers_jobs():
    names = {f.__name__ for f in WorkerSettings.functions}
    assert {"ingest_document", "send_email", "generate_tender_artifacts", "run_intelligence_pipeline"} <= names
    assert WorkerSettings.redis_settings.host == "redis"  # from redis_url dsn


def test_worker_settings_retries_killed_jobs():
    # A killed/failed job (e.g. generate_tender_artifacts interrupted by a deploy) must be retried
    # by arq rather than left stuck; its drafts stage is resumable, so a retry doesn't duplicate work.
    assert WorkerSettings.max_tries >= 2


def test_worker_settings_registers_sales_cron_jobs():
    by_name = {c.name: c for c in WorkerSettings.cron_jobs}
    assert {"sales_intel:scan_due_sources", "sales_intel:send_deadline_reminders"} <= set(by_name)
    # scan ticks every minute (minute unset), deadline reminder is dailyAt 08:00.
    assert by_name["sales_intel:scan_due_sources"].minute is None
    assert by_name["sales_intel:send_deadline_reminders"].hour == 8
    assert by_name["sales_intel:send_deadline_reminders"].minute == 0


def test_worker_settings_registers_invoice_reconciliation_cron():
    by_name = {c.name: c for c in WorkerSettings.cron_jobs}
    assert "billing:reconcile_invoices" in by_name
    assert by_name["billing:reconcile_invoices"].hour == 3
    assert by_name["billing:reconcile_invoices"].minute == 0


def test_get_task_queue_defaults_to_eager():
    assert isinstance(get_task_queue(registry), EagerTaskQueue)


def test_get_task_queue_selects_arq(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "task_backend", "arq")
    assert isinstance(get_task_queue(registry), ArqTaskQueue)


# --- _build_sales_runtime: the cron sweep's own OpportunityService wiring ---
#
# scan_due_sources/send_deadline_reminders are the PRIMARY, continuous background-scan path this
# feature exists for (the manually-triggered API scan in app.main is secondary). Without
# task_queue/pipeline_run_store wired here, a "Review" notice found by the cron sweep could never
# reach the agentic qualification pipeline -- only a manual API-triggered scan could.
class _FakeRedisPool:
    """Stands in for ctx["redis"] (the arq worker's own connection pool). Records enqueue_job
    calls instead of touching a real Redis, and proves _build_sales_runtime reuses this exact pool
    rather than opening a new one."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def enqueue_job(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return None


def test_build_sales_runtime_wires_task_queue_onto_the_worker_pool():
    """task_queue must be an ArqTaskQueue wrapping ctx["redis"] itself (no new pool), and
    pipeline_run_store must be the same Postgres-backed store app.main wires for the manual scan
    path -- both None (the pre-fix behaviour) is exactly the bug this test guards against."""
    from app.db.stores import SqlPipelineRunStore
    from app.tasks.worker import _build_sales_runtime

    fake_pool = _FakeRedisPool()
    service, agents, ingest_filters = _build_sales_runtime(sessionmaker=None, redis=fake_pool)

    assert isinstance(service.task_queue, ArqTaskQueue)
    assert service.task_queue._pool is fake_pool  # reused, not a freshly-opened pool
    assert isinstance(service.pipeline_run_store, SqlPipelineRunStore)
    assert agents is not None
    assert ingest_filters is not None


def test_build_sales_runtime_without_redis_disables_the_task_queue():
    """Defensive fallback: if ctx ever lacked "redis" (arq always sets it before any job runs),
    the cron sweep must behave exactly as it did before this fix (no task_queue) rather than
    reaching for a real Redis connection it was never given."""
    from app.tasks.worker import _build_sales_runtime

    service, _agents, _ingest_filters = _build_sales_runtime(sessionmaker=None, redis=None)
    assert service.task_queue is None


async def test_scan_due_sources_enqueues_the_agentic_pipeline_for_a_review_notice(monkeypatch):
    """End-to-end proof of the cron path: app.tasks.worker.scan_due_sources (the arq entrypoint
    the scheduled sweep actually calls) must enqueue run_idg_qualification_pipeline for a
    Review-scored notice, the same way the manually-triggered API scan does (see
    test_sales_intelligence.py::test_review_notice_enqueues_agentic_pipeline_and_bid_notice_does_not).
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.base import Base
    from app.db.stores import SqlAgentStore, SqlPipelineRunStore
    from app.modules.agents.service import Agent
    from app.modules.sales_intelligence.connectors import TedNoticeConnector
    from app.tasks import worker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    # An enabled agent so scan_due_sources's require_available_worker() gate does not skip the
    # source as WorkerUnavailable before ever reaching the connector.
    await SqlAgentStore(sessionmaker).add(
        Agent(id="agent-1", tenant="acme", name="Sales", atype="sales_intelligence", status="ready"))

    # Persist an active TED source the same way the manual "attach + enable" API flow would.
    setup_service, _setup_agents, _setup_filters = worker._build_sales_runtime(sessionmaker)
    await setup_service.update_source_status("acme", "agent-1", "ted", "active")

    # Same "Review" fixture test_sales_intelligence.py uses: one keyword hit, no country, no
    # estimated_value -> qualify() reports missing_fields/risks, so build_facets() is non-empty
    # and the cost-control gate in _scan_source fires.
    def fake_search(self, filters=None):
        return {"payload": {}, "skipped": 0, "notices": [{
            "external_id": "REVIEW-CRON-1", "title": "Risk advisory and audit services",
            "buyer": "Ministry of Advisory Affairs",
            "deadline_at": datetime.now(timezone.utc) + timedelta(days=45),
        }]}

    monkeypatch.setattr(TedNoticeConnector, "search", fake_search)
    fake_pool = _FakeRedisPool()
    ctx = {"sessionmaker": sessionmaker, "redis": fake_pool}
    summary = await worker.scan_due_sources(ctx)

    assert summary["scanned"] == 1
    assert summary["failed"] == 0

    enqueued = [call for call in fake_pool.calls if call[0] == "run_idg_qualification_pipeline"]
    assert len(enqueued) == 1
    _, kwargs = enqueued[0]
    assert kwargs["tenant"] == "acme"
    assert kwargs["agent_id"] == "agent-1"
    assert kwargs["run_id"]

    # The pipeline run this enqueue references was actually persisted (durably, not in-memory),
    # proving pipeline_run_store is wired end to end and not just non-None.
    persisted = await SqlPipelineRunStore(sessionmaker).get("acme", "agent-1", kwargs["run_id"])
    assert persisted is not None
    assert persisted.subject == "Risk advisory and audit services"
