"""arq worker entrypoint. Run with: `arq app.tasks.worker.WorkerSettings`.

Each registered job is wrapped to arq's (ctx, **kwargs) calling convention. A DB sessionmaker is
built once at worker startup and kept on the arq context, so jobs share one engine.
"""
from __future__ import annotations

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.tasks import jobs


async def ingest_document(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    return await jobs.ingest_document(**kwargs)


async def send_email(ctx, **kwargs):  # pragma: no cover - invoked by the arq runtime
    return await jobs.send_email(**kwargs)


FUNCTIONS = [ingest_document, send_email]


async def on_startup(ctx) -> None:  # pragma: no cover - worker runtime
    from app.core.db import build_engine, build_sessionmaker

    engine = build_engine()
    ctx["engine"] = engine
    ctx["sessionmaker"] = build_sessionmaker(engine)


async def on_shutdown(ctx) -> None:  # pragma: no cover - worker runtime
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    """arq worker configuration (worker-default; ingest/voice queues use the same functions)."""

    functions = FUNCTIONS
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
