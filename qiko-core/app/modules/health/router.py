"""Health and readiness endpoints (used by Docker/Caddy healthchecks)."""
from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "qiko-core",
        "version": __version__,
        "environment": settings.environment.value,
    }
