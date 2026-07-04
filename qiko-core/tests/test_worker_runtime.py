from app.tasks.jobs import registry
from app.tasks.queue import ArqTaskQueue, EagerTaskQueue, get_task_queue
from app.tasks.worker import WorkerSettings


def test_worker_settings_registers_jobs():
    names = {f.__name__ for f in WorkerSettings.functions}
    assert {"ingest_document", "send_email"} <= names
    assert WorkerSettings.redis_settings.host == "redis"  # from redis_url dsn


def test_get_task_queue_defaults_to_eager():
    assert isinstance(get_task_queue(registry), EagerTaskQueue)


def test_get_task_queue_selects_arq(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "task_backend", "arq")
    assert isinstance(get_task_queue(registry), ArqTaskQueue)
