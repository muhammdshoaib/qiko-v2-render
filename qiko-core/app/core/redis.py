"""Redis client factory (cache, queue, sessions, locks, rate limits)."""
from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings


def build_redis(redis_url: str | None = None) -> Redis:
    """Create an async Redis client. Lazy connection, so this is unit-testable."""
    url = redis_url or get_settings().redis_url
    return Redis.from_url(url, encoding="utf-8", decode_responses=True)
