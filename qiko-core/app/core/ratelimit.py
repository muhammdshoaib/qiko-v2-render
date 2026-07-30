"""Rate limiter. In-memory fixed-window now; a Redis-backed limiter slots in behind the same
protocol for multi-instance deployments."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class RateLimiter(Protocol):
    def allow(self, key: str) -> bool: ...


@dataclass
class RedisRateLimiter:
    _SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return count <= tonumber(ARGV[1]) and 1 or 0
"""

    def __init__(self, *, redis: Any, namespace: str, limit: int, window_seconds: int = 60) -> None:
        self.redis = redis
        self.namespace = namespace
        self.limit = limit
        self.window_seconds = window_seconds

    async def allow(self, key: str) -> bool:
        result = await self.redis.eval(
            self._SCRIPT, 1, f"{self.namespace}:{key}", self.limit, self.window_seconds)
        return bool(result)


@dataclass
class InMemoryRateLimiter:
    limit: int
    window_seconds: int = 60
    _hits: dict[str, tuple[int, float]] = field(default_factory=dict)

    def _now(self) -> float:
        return time.monotonic()

    def allow(self, key: str) -> bool:
        now = self._now()
        count, start = self._hits.get(key, (0, now))
        if now - start >= self.window_seconds:
            count, start = 0, now  # window expired, reset
        count += 1
        self._hits[key] = (count, start)
        return count <= self.limit
