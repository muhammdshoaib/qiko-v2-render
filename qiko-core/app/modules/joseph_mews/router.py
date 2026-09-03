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

from enum import StrEnum

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings, get_settings
from app.core.deps import get_agents
from app.modules.agents.router import verify_worker_api_key
from app.modules.agents.service import Agent, AgentService
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


async def _get_joseph_mews_agent(agents: AgentService) -> Agent | None:
    """None before the Agent is provisioned, or on a lookup failure -- never raises. Callers
    (auth and config resolution alike) treat that exactly like the Agent never existed."""
    try:
        return await agents.get(TENANT, AGENT_ID)
    except Exception:  # noqa: BLE001 - a lookup failure must not block generation or auth
        return None


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


class GenerationOutcome(StrEnum):
    """Whether a previously-generated summary/insight turned out to be accurate once a human (or
    the downstream system tracking the investor's actual response) could judge it. This is
    QUALITY tracking for the analytics view, not a grounding input -- unlike AgentCore's
    verified-answers flywheel (Worker.approve()), each signal/insight is about a unique
    investor+property+moment, so there is no recurring "same topic" for an approved answer to
    usefully override next time. Recorded so "how often is this worker right" is an answerable
    question, not fed back into future prompts."""

    accurate = "accurate"
    inaccurate = "inaccurate"


class OutcomeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: GenerationOutcome
    note: str = Field(default="", max_length=2000)


@dataclass
class _OutcomeLog:
    """In-memory outcome counts per generation kind ('signal'/'insight'). Same single-replica
    tradeoff as _ResultCache -- needs a real store before scaling past one instance."""

    max_entries: int = 10_000
    _by_request: OrderedDict[str, OutcomeReport] = field(default_factory=OrderedDict)

    def record(self, request_id: str, report: OutcomeReport) -> None:
        self._by_request[request_id] = report
        while len(self._by_request) > self.max_entries:
            self._by_request.popitem(last=False)

    def counts(self) -> dict[str, int]:
        counts = {outcome.value: 0 for outcome in GenerationOutcome}
        for report in self._by_request.values():
            counts[report.outcome.value] += 1
        return counts


_signal_outcomes = _OutcomeLog()
_insight_outcomes = _OutcomeLog()


async def require_worker_caller(
    tenant_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    agents: Annotated[AgentService, Depends(get_agents)],
    x_api_key: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> Agent | None:
    """Authenticates ANY authorised caller of this worker API -- jm-backend, joseph-mews-backend,
    or any other system with the shared key, not one specific consumer (the name/module docstring
    predates that; kept general on purpose now). Also resolves the joseph-mews Agent once here so
    the endpoint below reuses it for guardrails instead of a second lookup.

    Two valid keys during the migration to self-service (POST /agents/{id}/worker-api-key):
    the Agent's own generated key takes priority once one exists; settings.jm_backend_api_key
    (the original env-configured secret) still works as a fallback so already-configured
    environments are not broken by this ever having shipped as env-only."""
    if tenant_id != _KNOWN_TENANT or x_tenant_id != _KNOWN_TENANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown tenant")
    agent = await _get_joseph_mews_agent(agents)
    if verify_worker_api_key(agent, x_api_key or ""):
        return agent
    configured = settings.jm_backend_api_key
    agent_key_configured = bool(agent and agent.config.get("worker_api_key_hash"))
    if not configured and not agent_key_configured:
        if not settings.debug:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "worker API key not configured")
        return agent
    if configured and x_api_key and hmac.compare_digest(x_api_key, configured):
        return agent
    raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or missing API key")


@router.post("/signals/summarize")
async def summarize_signal_endpoint(
    tenant_id: str, body: SignalSummarizeRequest,
    agent: Annotated[Agent | None, Depends(require_worker_caller)],
) -> dict:
    seen, cached = _cache.get(body.requestId)
    if seen:
        return _signal_response(body.requestId, cached)

    config = agent.config if agent is not None else None
    result = await asyncio.to_thread(summarize_signal, body, get_provider(), config)
    _cache.put(body.requestId, result)
    return _signal_response(body.requestId, result)


@router.post("/insights/property")
async def property_insight_endpoint(
    tenant_id: str, body: PropertyInsightRequest,
    agent: Annotated[Agent | None, Depends(require_worker_caller)],
) -> dict:
    seen, cached = _insight_cache.get(body.requestId)
    if seen:
        return _insight_response(body.requestId, cached)

    config = agent.config if agent is not None else None
    result = await asyncio.to_thread(generate_property_insight, body, get_provider(), config)
    _insight_cache.put(body.requestId, result)
    return _insight_response(body.requestId, result)


@router.post("/signals/{request_id}/outcome")
async def report_signal_outcome(
    tenant_id: str, request_id: str, body: OutcomeReport,
    _agent: Annotated[Agent | None, Depends(require_worker_caller)],
) -> dict:
    """Backward data flow (3 Sep, Razvan): a consumer that generated a signal summary reports
    whether it turned out accurate once a human could judge it. Any authorised caller can report
    an outcome, not only the one that requested the original summary -- outcomes commonly surface
    downstream of where the generation happened (e.g. an admin acting on the signal in
    joseph-mews-backend, not jm-backend)."""
    seen, _ = _cache.get(request_id)
    if not seen:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown requestId")
    _signal_outcomes.record(request_id, body)
    return {"requestId": request_id, "recorded": True}


@router.post("/insights/{request_id}/outcome")
async def report_insight_outcome(
    tenant_id: str, request_id: str, body: OutcomeReport,
    _agent: Annotated[Agent | None, Depends(require_worker_caller)],
) -> dict:
    seen, _ = _insight_cache.get(request_id)
    if not seen:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown requestId")
    _insight_outcomes.record(request_id, body)
    return {"requestId": request_id, "recorded": True}


@router.get("/outcomes/summary")
async def outcomes_summary(
    tenant_id: str, _agent: Annotated[Agent | None, Depends(require_worker_caller)],
) -> dict:
    return {"signals": _signal_outcomes.counts(), "insights": _insight_outcomes.counts()}


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
