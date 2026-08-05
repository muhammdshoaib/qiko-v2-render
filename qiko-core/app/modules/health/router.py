"""Health and readiness endpoints (used by Docker/Caddy healthchecks)."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app import __version__
from app.core.config import get_settings
from app.modules.health.system import readiness

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness. Deliberately does NOT probe dependencies.

    A liveness probe that fails during a database blip makes Docker restart a healthy container,
    turning a brief dependency outage into a crash loop and a longer one. Readiness is the endpoint
    that answers "can this instance actually serve" -- see /health/ready.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "service": "qiko-core",
        "version": __version__,
        "environment": settings.environment.value,
    }


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict:
    """Readiness: 200 only when every dependency answers, 503 otherwise.

    Nothing had this distinction, so /health returned a static dict and a deploy could be declared
    successful against an unreachable database. Unauthenticated on purpose: a load balancer and the
    deploy gate need it, and it reveals only whether a dependency answered, never why in a form that
    could leak a connection string.
    """
    ok, probes = await readiness(request.app.state)
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ok else "not_ready",
            "checks": [probe.as_dict() for probe in probes]}
