"""Cached Qiko Track delivery metrics for the Intelligence Worker status view and chat.

Metrics are read, never computed here. `loadMetrics` on the Qiko Track side owns the
numbers so the worker cannot disagree with the source of truth.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.modules.intelligence.qiko_track_client import QikoTrackClient, QikoTrackClientError


@dataclass
class _CachedMetrics:
    fetched_at: float
    data: dict[str, Any]


@dataclass
class MetricsService:
    """Fetch and cache Qiko Track project metrics with a short TTL.

    The cache is per-instance, suitable for a single request or a long-lived app
    service. A hit avoids repeated API calls inside one chat session.
    """

    base_url: str
    token: str
    ttl_seconds: float = 60.0
    _cache: dict[str, _CachedMetrics] = field(default_factory=dict, repr=False)

    async def for_projects(self, project_keys: list[str], *, window: str = "30d",
                           sprint: int | None = None) -> dict[str, dict[str, Any]]:
        """Return metrics for each project key, with per-key TTL caching.

        Missing or failed projects are returned with ``available: false`` and a
        short error message so callers can degrade honestly.
        """
        now = time.monotonic()
        results: dict[str, dict[str, Any]] = {}
        client = QikoTrackClient(self.base_url, self.token)

        for key in project_keys:
            cache_key = f"{key}:{window}:{sprint}"
            cached = self._cache.get(cache_key)
            if cached and (now - cached.fetched_at) < self.ttl_seconds:
                results[key] = cached.data
                continue

            try:
                data = await client.get_metrics(key, window=window, sprint=sprint)
            except QikoTrackClientError as exc:
                data = {"available": False, "error": str(exc)}
            else:
                data = {"available": True, **data}

            self._cache[cache_key] = _CachedMetrics(fetched_at=now, data=data)
            results[key] = data

        return results
