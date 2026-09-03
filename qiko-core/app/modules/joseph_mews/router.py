"""Worker-facing API for jm-backend (JM2-1065/1066), distinct from channels/router.py's
Interakt webhook: this is jm-backend calling INTO qiko-core for AI generation, not an inbound
customer message. Service-to-service, not a logged-in tenant session.
"""

from __future__ import annotations

import asyncio
import hmac
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.deps import get_agents
from app.modules.agents.service import AgentService
from app.modules.ai.gateway import get_provider
from app.modules.joseph_mews.portfolio_insights import (
    PropertyInsightRequest,
    PropertyInsightResult,
    generate_property_insight,
)
from app.modules.joseph_mews.signal_summary import (
    SignalSummarizeRequest,
    SignalSummaryResult,
    summarize_signal,
)
from app.modules.joseph_mews.worker import AGENT_ID, TENANT

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["joseph-mews-worker"])

# Only tenant this worker API serves today; the contract's {tenantId} path segment is forward
# looking (JM2-1066: "propose this ourselves, not yet allocated" beyond this one client).
_KNOWN_TENANT = "joseph-mews"


async def _agent_config(agents: AgentService) -> dict | None:
    """The joseph-mews Creator Agent's config (Rules/Guardrails/Prompts), or None before it's
    provisioned. Never raises: a lookup failure here must not block generation, it should just
    fall back to guardrails.py's SHARED_GUARDRAILS like the Agent never existed."""
    try:
        agent = await agents.get(TENANT, AGENT_ID)
    except Exception:  # noqa: BLE001 - config lookup must not break generation
        return None
    return agent.config if agent is not None else None


@dataclass
class _ResultCache:
    """Caches a completed generation result per requestId so a retried call after a
    client-side timeout returns the same result instead of drafting a second, possibly
    different, one. Shared by both generation endpoints below (signal summaries, property
    insights) since both need exactly the same idempotency behaviour. Same bounded/in-memory
    tradeoff as channels.webhooks.IdempotencyGuard: fine for a single replica, needs Redis
    before scaling out."""

    max_entries: int = 10_000
    _results: OrderedDict[str, SignalSummaryResult | PropertyInsightResult | None] = field(
        default_factory=OrderedDict
    )

    def get(self, request_id: str) -> tuple[bool, SignalSummaryResult | PropertyInsightResult | None]:
        if request_id in self._results:
            return True, self._results[request_id]
        return False, None

    def put(self, request_id: str, result: SignalSummaryResult | PropertyInsightResult | None) -> None:
        self._results[request_id] = result
        while len(self._results) > self.max_entries:
            self._results.popitem(last=False)


_cache = _ResultCache()
_insight_cache = _ResultCache()


async def require_jm_backend(
    tenant_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> None:
    if tenant_id != _KNOWN_TENANT or x_tenant_id != _KNOWN_TENANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown tenant")
    configured = settings.jm_backend_api_key
    if not configured:
        if not settings.debug:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "worker API key not configured")
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, configured):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or missing API key")


@router.post("/signals/summarize", dependencies=[Depends(require_jm_backend)])
async def summarize_signal_endpoint(
    tenant_id: str, body: SignalSummarizeRequest,
    agents: Annotated[AgentService, Depends(get_agents)],
) -> dict:
    seen, cached = _cache.get(body.requestId)
    if seen:
        return _signal_response(body.requestId, cached)

    config = await _agent_config(agents)
    result = await asyncio.to_thread(summarize_signal, body, get_provider(), config)
    _cache.put(body.requestId, result)
    return _signal_response(body.requestId, result)


@router.post("/insights/property", dependencies=[Depends(require_jm_backend)])
async def property_insight_endpoint(
    tenant_id: str, body: PropertyInsightRequest,
    agents: Annotated[AgentService, Depends(get_agents)],
) -> dict:
    seen, cached = _insight_cache.get(body.requestId)
    if seen:
        return _insight_response(body.requestId, cached)

    config = await _agent_config(agents)
    result = await asyncio.to_thread(generate_property_insight, body, get_provider(), config)
    _insight_cache.put(body.requestId, result)
    return _insight_response(body.requestId, result)


def _signal_response(request_id: str, result: SignalSummaryResult | None) -> dict:
    if result is None:
        return {
            "requestId": request_id,
            "error": {"code": "GENERATION_FAILED", "message": "could not draft a grounded summary"},
        }
    return {
        "requestId": request_id,
        "summary": result.summary,
        "suggestedNextAction": result.suggestedNextAction,
        "groundedIn": result.groundedIn,
    }


def _insight_response(request_id: str, result: PropertyInsightResult | None) -> dict:
    if result is None:
        return {
            "requestId": request_id,
            "error": {"code": "GENERATION_FAILED", "message": "could not draft a grounded insight"},
        }
    return {"requestId": request_id, "summary": result.summary, "groundedIn": result.groundedIn}
