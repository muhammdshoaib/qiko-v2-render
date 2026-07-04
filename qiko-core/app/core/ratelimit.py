"""Rate limiter. In-memory fixed-window now; a Redis-backed limiter slots in behind the same
protocol for multi-instance deployments."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


class RateLimiter(Protocol):
    def allow(self, key: str) -> bool: ...


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
