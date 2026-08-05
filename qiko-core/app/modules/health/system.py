"""Dependency probes and system statistics (QIK-518).

Why /health is left alone
-------------------------
`/health` is the container liveness probe. It must answer 200 whenever the process is able to serve,
and it deliberately does NOT check Postgres or Redis: a liveness probe that fails during a database
blip makes Docker restart a perfectly healthy container, turning a brief dependency outage into a
crash loop and a longer one.

`/health/ready` is the readiness probe and does check dependencies, so a deploy gate or a load
balancer can tell the difference between "the process is up" and "the process can actually serve".
Nothing had that distinction before: /health returned a static dict, so a deploy could be declared
successful with an unreachable database.
"""
from __future__ import annotations

import asyncio
import os
import platform
import resource
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

_STARTED_AT = time.monotonic()
_STARTED_WALL = datetime.now(timezone.utc)

# A probe must never hang a request. If a dependency cannot answer in this long it is not ready,
# which is the same conclusion a caller would reach anyway, and far better than holding the
# connection open until the client times out.
PROBE_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class Probe:
    name: str
    ok: bool
    detail: str | None = None
    latency_ms: int | None = None

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail,
                "latency_ms": self.latency_ms}


async def _timed(name: str, coroutine) -> Probe:
    started = time.monotonic()
    try:
        detail = await asyncio.wait_for(coroutine, timeout=PROBE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return Probe(name=name, ok=False, detail=f"timed out after {PROBE_TIMEOUT_SECONDS:g}s",
                     latency_ms=int((time.monotonic() - started) * 1000))
    except Exception as error:  # noqa: BLE001 - a probe reports failure, it does not raise
        # The message is a class name plus a short reason on purpose: a raw driver error can contain
        # the connection string, and this endpoint is reachable by a load balancer.
        return Probe(name=name, ok=False, detail=type(error).__name__,
                     latency_ms=int((time.monotonic() - started) * 1000))
    return Probe(name=name, ok=True, detail=detail,
                 latency_ms=int((time.monotonic() - started) * 1000))


async def probe_database(sessionmaker) -> Probe:
    if sessionmaker is None:
        return Probe(name="database", ok=True, detail="in-memory stores")

    async def check() -> str:
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
            return "reachable"

    return await _timed("database", check())


async def probe_redis(redis) -> Probe:
    if redis is None:
        return Probe(name="redis", ok=True, detail="not configured")

    async def check() -> str:
        await redis.ping()
        return "reachable"

    return await _timed("redis", check())


async def readiness(app_state) -> tuple[bool, list[Probe]]:
    """Every dependency probed concurrently, so a slow one does not serialise behind another."""
    probes = await asyncio.gather(
        probe_database(getattr(app_state, "sessionmaker", None)),
        probe_redis(getattr(app_state, "redis", None)),
    )
    return all(probe.ok for probe in probes), list(probes)


def process_stats() -> dict:
    """Process facts from the standard library only.

    Deliberately no psutil: a new runtime dependency for numbers the stdlib already exposes is extra
    supply-chain surface on a service that handles customer data.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # ru_maxrss is kilobytes on Linux and bytes on macOS. Normalise, and say which was assumed.
    max_rss_kb = usage.ru_maxrss if sys.platform != "darwin" else usage.ru_maxrss // 1024
    return {
        "uptime_seconds": int(time.monotonic() - _STARTED_AT),
        "started_at": _STARTED_WALL.isoformat(),
        "pid": os.getpid(),
        "python": platform.python_version(),
        "platform": sys.platform,
        "max_rss_kb": int(max_rss_kb),
        "cpu_user_seconds": round(usage.ru_utime, 2),
        "cpu_system_seconds": round(usage.ru_stime, 2),
        # A load average is meaningful only relative to core count, so both or neither.
        "load_average": [round(value, 2) for value in os.getloadavg()] if hasattr(os, "getloadavg") else None,
        "cpu_count": os.cpu_count(),
    }


async def database_stats(sessionmaker) -> dict:
    """Size and connection counts, on Postgres only.

    Guarded on the dialect rather than assumed: much of the test suite runs on SQLite, where these
    catalogue views do not exist, and a dashboard that 500s in dev is a dashboard nobody trusts.
    """
    if sessionmaker is None:
        return {"available": False, "reason": "in-memory stores"}
    try:
        async with sessionmaker() as session:
            dialect = session.bind.dialect.name if session.bind is not None else "unknown"
            if dialect != "postgresql":
                return {"available": False, "reason": f"dialect {dialect}"}
            size = (await session.execute(
                text("SELECT pg_database_size(current_database())"))).scalar_one()
            connections = (await session.execute(text(
                "SELECT count(*), count(*) FILTER (WHERE state = 'active') "
                "FROM pg_stat_activity WHERE datname = current_database()"))).one()
            limit = (await session.execute(text("SHOW max_connections"))).scalar_one()
            return {"available": True, "size_bytes": int(size),
                    "connections_total": int(connections[0]),
                    "connections_active": int(connections[1]),
                    "connections_limit": int(limit)}
    except Exception as error:  # noqa: BLE001 - statistics must not break the dashboard
        return {"available": False, "reason": type(error).__name__}


async def redis_stats(redis) -> dict:
    if redis is None:
        return {"available": False, "reason": "not configured"}
    try:
        info = await asyncio.wait_for(redis.info(), timeout=PROBE_TIMEOUT_SECONDS)
        return {"available": True,
                "used_memory_bytes": int(info.get("used_memory") or 0),
                "max_memory_bytes": int(info.get("maxmemory") or 0),
                "connected_clients": int(info.get("connected_clients") or 0),
                "evicted_keys": int(info.get("evicted_keys") or 0),
                # A non-zero rejected count means the connection limit was hit, which is the failure
                # mode that shows up as random request errors rather than as an outage.
                "rejected_connections": int(info.get("rejected_connections") or 0),
                "uptime_seconds": int(info.get("uptime_in_seconds") or 0)}
    except Exception as error:  # noqa: BLE001
        return {"available": False, "reason": type(error).__name__}


async def queue_stats(redis, queue_name: str = "arq:queue") -> dict:
    """Background queue depth. A growing queue is the earliest signal that the worker tier is stuck,
    and nothing surfaced it before."""
    if redis is None:
        return {"available": False, "reason": "not configured"}
    try:
        depth = await asyncio.wait_for(redis.zcard(queue_name), timeout=PROBE_TIMEOUT_SECONDS)
        return {"available": True, "queue": queue_name, "depth": int(depth or 0)}
    except Exception as error:  # noqa: BLE001
        return {"available": False, "reason": type(error).__name__}
