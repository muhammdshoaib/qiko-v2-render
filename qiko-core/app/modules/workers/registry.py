"""Registry of worker instances, so the platform can list and resolve client workers by name."""
from __future__ import annotations

from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import Worker, build_worker


class WorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[str, Worker] = {}

    def register(self, config: WorkerConfig, **kw) -> Worker:
        worker = build_worker(config, **kw)
        self._workers[config.name] = worker
        return worker

    def get(self, name: str) -> Worker | None:
        return self._workers.get(name)

    def names(self) -> list[str]:
        return sorted(self._workers)
