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
from app.modules.ai.gateway import get_provider
from app.modules.joseph_mews.signal_summary import (
    SignalSummarizeRequest,
    SignalSummaryResult,
    summarize_signal,
)

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["joseph-mews-worker"])

# Only tenant this worker API serves today; the contract's {tenantId} path segment is forward
# looking (JM2-1066: "propose this ourselves, not yet allocated" beyond this one client).
_KNOWN_TENANT = "joseph-mews"


@dataclass
class _ResultCache:
    """Caches a completed summarize result per requestId so a retried call after a client-side
    timeout returns the same result instead of drafting a second, possibly different, summary.
    Same bounded/in-memory tradeoff as channels.webhooks.IdempotencyGuard: fine for a single
    replica, needs Redis before scaling out."""

    max_entries: int = 10_000
    _results: OrderedDict[str, SignalSummaryResult | None] = field(default_factory=OrderedDict)

    def get(self, request_id: str) -> tuple[bool, SignalSummaryResult | None]:
        if request_id in self._results:
            return True, self._results[request_id]
        return False, None

    def put(self, request_id: str, result: SignalSummaryResult | None) -> None:
        self._results[request_id] = result
        while len(self._results) > self.max_entries:
            self._results.popitem(last=False)


_cache = _ResultCache()


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
async def summarize_signal_endpoint(tenant_id: str, body: SignalSummarizeRequest) -> dict:
    seen, cached = _cache.get(body.requestId)
    if seen:
        return _response(body.requestId, cached)

    result = await asyncio.to_thread(summarize_signal, body, get_provider())
    _cache.put(body.requestId, result)
    return _response(body.requestId, result)


def _response(request_id: str, result: SignalSummaryResult | None) -> dict:
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
