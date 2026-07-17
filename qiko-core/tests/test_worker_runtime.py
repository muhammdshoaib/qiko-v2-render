from app.tasks.jobs import registry
from app.tasks.queue import ArqTaskQueue, EagerTaskQueue, get_task_queue
from app.tasks.worker import WorkerSettings


def test_worker_settings_registers_jobs():
    names = {f.__name__ for f in WorkerSettings.functions}
    assert {"ingest_document", "send_email", "generate_tender_artifacts"} <= names
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


def test_get_task_queue_defaults_to_eager():
    assert isinstance(get_task_queue(registry), EagerTaskQueue)


def test_get_task_queue_selects_arq(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "task_backend", "arq")
    assert isinstance(get_task_queue(registry), ArqTaskQueue)
