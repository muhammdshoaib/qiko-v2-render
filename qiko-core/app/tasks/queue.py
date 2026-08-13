"""Task queue: a registry of async tasks plus interchangeable executors.

The API never does slow work inline; it enqueues a task. In dev/tests an Eager executor runs the
task immediately; in prod an arq executor puts it on Redis for the worker tier (worker-default,
worker-ingest, worker-voice) to pick up with retries/backoff.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


class TaskError(Exception):
    pass


@dataclass
class TaskRegistry:
    _tasks: dict[str, Callable[..., Awaitable[Any]]] = field(default_factory=dict)

    def register(self, name: str) -> Callable:
        def wrap(fn: Callable[..., Awaitable[Any]]) -> Callable:
            self._tasks[name] = fn
            return fn
        return wrap

    def get(self, name: str) -> Callable[..., Awaitable[Any]]:
        if name not in self._tasks:
            raise TaskError(f"unknown task: {name}")
        return self._tasks[name]

    def names(self) -> list[str]:
        return sorted(self._tasks)


@dataclass
class EagerTaskQueue:
    """Runs tasks inline. Used in dev/tests; proves the task functions work end to end."""

    registry: TaskRegistry

    async def enqueue(self, name: str, *, defer_by: Any = None, defer_until: Any = None,
                      **kwargs: Any) -> Any:
        # Eager ignores deferral and runs immediately; callers that need real delay use arq.
        return await self.registry.get(name)(**kwargs)


class ArqEnqueueError(Exception):
    pass


def get_task_queue(registry: TaskRegistry):
    """Select the queue backend from config: Eager inline (dev/tests) or arq on Redis (prod)."""
    from app.core.config import get_settings

    if get_settings().task_backend == "arq":  # pragma: no cover - needs Redis + worker
        return ArqTaskQueue(get_settings().redis_url)
    return EagerTaskQueue(registry)


@dataclass
class ArqTaskQueue:  # pragma: no cover - requires Redis + arq worker
    """Enqueues onto Redis for the arq worker tier."""

    redis_url: str
    _pool: Any = None

    async def _get_pool(self):
        from arq import create_pool
        from arq.connections import RedisSettings

        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(self.redis_url))
        return self._pool

    async def enqueue(self, name: str, *, defer_by: Any = None, defer_until: Any = None,
                      **kwargs: Any) -> Any:
        pool = await self._get_pool()
        arq_kwargs: dict[str, Any] = {}
        if defer_by is not None:
            arq_kwargs["_defer_by"] = defer_by
        if defer_until is not None:
            arq_kwargs["_defer_until"] = defer_until
        return await pool.enqueue_job(name, **arq_kwargs, **kwargs)
