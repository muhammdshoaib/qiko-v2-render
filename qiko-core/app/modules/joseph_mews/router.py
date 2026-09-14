"""Worker-facing API for jm-backend (JM2-1065/1066), distinct from channels/router.py's
Interakt webhook: this is jm-backend calling INTO qiko-core for AI generation, not an inbound
customer message. Service-to-service, not a logged-in tenant session.
"""

from __future__ import annotations

import asyncio
import hmac
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from enum import StrEnum

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings, get_settings
from app.core.deps import (
    get_agents,
    get_intent_signals,
    get_investor_activity_store,
    get_jm_generations,
    get_task_queue,
)
from app.modules.agents.router import verify_worker_api_key
from app.modules.agents.service import Agent, AgentService
from app.modules.ai.gateway import get_provider
from app.modules.joseph_mews.activity import (
    ACTIVITY_SORTS,
    DEFAULT_ACTIVITY_SORT,
    MAX_ACTIVITY_PAGE,
    MIN_CALCULATOR_VISITS_FOR_SIGNAL,
    MIN_PROPERTY_VISITS_FOR_SIGNAL,
    IntentSignalRequest,
    IntentSignalResult,
    IntentSignalStore,
    InvestorActivityStore,
    aggregate_activity,
    generate_intent_signals,
    has_signal_worthy_evidence,
)
from app.modules.joseph_mews.investor_token import InvestorTokenError, decode_investor_activity_token
from app.modules.joseph_mews.signal_scheduler import IntentSignalScheduler
from app.modules.joseph_mews.generations import GenerationKind
from app.modules.joseph_mews.portfolio_insights import (
    MAX_PORTFOLIO_INSIGHTS,
    PortfolioInsightsRequest,
    PortfolioInsightsResult,
    PropertyInsightRequest,
    PropertyInsightResult,
    generate_portfolio_insights,
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



def _investor_ref(body: object) -> str | None:
    """The investor this generation is about, for the GET lookup and per-investor reporting.

    Requests carry the investor as a free-form dict (`extra="allow"` on the request models), so
    this reads the two shapes callers actually send rather than requiring a schema change on their
    side: a top-level `investorRef`, or `investor.ref`/`investor.id`."""
    ref = getattr(body, "investorRef", None)
    if isinstance(ref, str) and ref:
        return ref
    investor = getattr(body, "investor", None)
    if isinstance(investor, dict):
        for key in ("ref", "investorRef", "id"):
            value = investor.get(key)
            if isinstance(value, (str, int)) and str(value):
                return str(value)
    return None


def _as_signal(stored: dict | None) -> SignalSummaryResult | None:
    return SignalSummaryResult.model_validate(stored) if stored else None


def _as_insight(stored: dict | None) -> PropertyInsightResult | None:
    return PropertyInsightResult.model_validate(stored) if stored else None


def _as_portfolio(stored: dict | None) -> PortfolioInsightsResult | None:
    return PortfolioInsightsResult.model_validate(stored) if stored else None


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
    store: Annotated[object, Depends(get_jm_generations)],
) -> dict:
    seen, cached = await store.get(tenant_id, body.requestId)
    if seen:
        return _signal_response(body.requestId, _as_signal(cached))

    config = agent.config if agent is not None else None
    result = await asyncio.to_thread(summarize_signal, body, get_provider(), config)
    await store.put(tenant_id, body.requestId, GenerationKind.signal,
                    result.model_dump() if result else None,
                    investor_ref=_investor_ref(body))
    return _signal_response(body.requestId, result)


@router.post("/insights/property")
async def property_insight_endpoint(
    tenant_id: str, body: PropertyInsightRequest,
    agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[object, Depends(get_jm_generations)],
) -> dict:
    seen, cached = await store.get(tenant_id, body.requestId)
    if seen:
        return _insight_response(body.requestId, _as_insight(cached))

    config = agent.config if agent is not None else None
    result = await asyncio.to_thread(generate_property_insight, body, get_provider(), config)
    await store.put(tenant_id, body.requestId, GenerationKind.property_insight,
                    result.model_dump() if result else None,
                    investor_ref=_investor_ref(body),
                    property_name=(body.property or {}).get("name"),
                    location=(body.property or {}).get("location"),
                    postcode=(body.property or {}).get("postcode"))
    return _insight_response(body.requestId, result)


@router.get("/insights/property")
async def get_property_insight(
    tenant_id: str, investorRef: str,
    _agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[object, Depends(get_jm_generations)],
    propertyName: str | None = None,
) -> dict:
    """Read back the most recent property insight for an investor, optionally for one named
    property.

    Added because the app had no way to display an insight it had already paid to generate: the
    only route was re-POSTing the same requestId, which only returned the original while the
    generating process was still alive. Asked for during integration (Shoaib, 10 Sep).

    `propertyName` rather than a property id, matching the identity rule the rest of this module
    enforces. Returns 404 when there is nothing stored, so the caller can tell "not generated yet"
    from "generated and empty".
    """
    stored = await store.latest_property_insight(tenant_id, investorRef,
                                                 property_name=propertyName)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no insight stored for that investor")
    result = _as_insight(stored)
    return {"investorRef": investorRef, "summary": result.summary, "groundedIn": result.groundedIn}


def _portfolio_insight_response(request_id: str, result: PortfolioInsightsResult | None) -> dict:
    if result is None:
        return {
            "requestId": request_id,
            "error": {"code": "GENERATION_FAILED", "message": "could not draft portfolio insights"},
        }
    return {"requestId": request_id, "cards": [c.model_dump() for c in result.cards]}


@router.post("/insights/portfolio")
async def portfolio_insights_endpoint(
    tenant_id: str, body: PortfolioInsightsRequest,
    agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[object, Depends(get_jm_generations)],
) -> dict:
    """JM2-1132: categorized portfolio-level cards (Concentration, Regional Performance, Income
    Performance, Pipeline), same idempotency-on-requestId behaviour as insights/property."""
    seen, cached = await store.get(tenant_id, body.requestId)
    if seen:
        return _portfolio_insight_response(body.requestId, _as_portfolio(cached))

    config = agent.config if agent is not None else None
    result = await asyncio.to_thread(generate_portfolio_insights, body, get_provider(), config)
    await store.put(tenant_id, body.requestId, GenerationKind.portfolio_insight,
                    result.model_dump() if result else None,
                    investor_ref=_investor_ref(body))
    return _portfolio_insight_response(body.requestId, result)


@router.get("/insights/portfolio")
async def get_portfolio_insights(
    tenant_id: str, investorRef: str,
    _agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[object, Depends(get_jm_generations)],
) -> dict:
    """Read back an investor's portfolio insights: 1 to 3 cards covering their own portfolio and,
    where the caller supplied platformAverages when generating, how it sits against the wider
    Joseph Mews portfolio (JM2-1133).

    A read of what was already drafted, like GET /insights/property: the admin panel and the app
    both display these on load, and regenerating per view would spend model budget to restate the
    same grounded facts. 404 when nothing has been generated for the investor yet, so the caller
    can tell that apart from an investor whose portfolio genuinely supports no card.
    """
    stored = await store.latest_portfolio_insight(tenant_id, investorRef)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "no portfolio insights stored for that investor")
    result = _as_portfolio(stored)
    return {
        "investorRef": investorRef,
        "cards": [c.model_dump() for c in result.cards[:MAX_PORTFOLIO_INSIGHTS]],
    }


@router.post("/signals/{request_id}/outcome")
async def report_signal_outcome(
    tenant_id: str, request_id: str, body: OutcomeReport,
    _agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[object, Depends(get_jm_generations)],
) -> dict:
    """Backward data flow (3 Sep, Razvan): a consumer that generated a signal summary reports
    whether it turned out accurate once a human could judge it. Any authorised caller can report
    an outcome, not only the one that requested the original summary -- outcomes commonly surface
    downstream of where the generation happened (e.g. an admin acting on the signal in
    joseph-mews-backend, not jm-backend)."""
    if not await store.record_outcome(tenant_id, request_id, body.outcome.value, body.note):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown requestId")
    return {"requestId": request_id, "recorded": True}


@router.post("/insights/{request_id}/outcome")
async def report_insight_outcome(
    tenant_id: str, request_id: str, body: OutcomeReport,
    _agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[object, Depends(get_jm_generations)],
) -> dict:
    # Covers both insight shapes (per-property, JM2-1042, and portfolio-level, JM2-1132) under
    # one outcome log -- a requestId is unique to whichever one generated it, so there is no
    # ambiguity in accepting a report against either cache here.
    if not await store.record_outcome(tenant_id, request_id, body.outcome.value, body.note):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown requestId")
    return {"requestId": request_id, "recorded": True}


@router.get("/outcomes/summary")
async def outcomes_summary(
    tenant_id: str, _agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[object, Depends(get_jm_generations)],
) -> dict:
    """Quality tracking, not a product surface: how often a generated signal or insight was judged
    accurate once a human could tell. Counted from storage now, so a release no longer resets it
    to zero."""
    signals = await store.counts(tenant_id, GenerationKind.signal)
    prop = await store.counts(tenant_id, GenerationKind.property_insight)
    portfolio = await store.counts(tenant_id, GenerationKind.portfolio_insight)
    return {
        "signals": signals.as_dict(),
        "insights": {
            "accurate": prop.accurate + portfolio.accurate,
            "inaccurate": prop.inaccurate + portfolio.inaccurate,
        },
    }


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


async def require_investor_token(tenant_id: str, authorization: Annotated[str | None, Header()] = None) -> str:
    """Authenticates one investor's own mobile app for the activity-write path (JM2-1131) --
    distinct from require_worker_caller, which authenticates a whole backend on behalf of the
    tenant. Returns the investor_ref claim. Deliberately does not accept X-Api-Key: a leaked
    worker key must not let a caller impersonate an individual investor's own activity feed."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        claims = decode_investor_activity_token(token)
    except InvestorTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    if claims["tenant"] != tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token tenant mismatch")
    return claims["investor_ref"]


class PostActivityRequest(BaseModel):
    """extra="forbid" is deliberate: a stray propertyId/developmentId/documentId must be a hard
    422, not a silently-accepted-and-ignored field, so a client-side regression that starts
    sending ids again is caught immediately rather than passing review by accident."""

    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=255)
    propertyName: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    postcode: str | None = Field(default=None, max_length=16)


@router.post("/activity", status_code=status.HTTP_201_CREATED)
async def post_activity(
    tenant_id: str, body: PostActivityRequest,
    investor_ref: Annotated[str, Depends(require_investor_token)],
    store: Annotated[InvestorActivityStore, Depends(get_investor_activity_store)],
    queue: Annotated[object, Depends(get_task_queue)],
) -> dict:
    await store.record(
        tenant_id, investor_ref, category=body.category, label=body.label,
        property_name=body.propertyName, location=body.location, postcode=body.postcode,
    )
    # Schedule the intent signal draft for this investor (JM2-1134). This is what populates the
    # cross-investor feed: without it, signals only ever exist for investors somebody already
    # opened individually, which is the per-investor querying that feed exists to replace.
    # Deliberately after the write and deliberately unable to fail it: see on_activity.
    await IntentSignalScheduler(task_queue=queue).on_activity(tenant_id, investor_ref)
    return {"status": "recorded"}


def _activity_json(event) -> dict:
    return {
        "investorRef": event.investor_ref,
        "category": event.category, "label": event.label, "propertyName": event.property_name,
        "location": event.location, "postcode": event.postcode,
        "occurredAt": event.occurred_at.isoformat() if event.occurred_at else None,
    }


@router.get("/activity")
async def get_activity(
    tenant_id: str,
    _agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[InvestorActivityStore, Depends(get_investor_activity_store)],
    investorRef: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=32),
    since: datetime | None = None,
    until: datetime | None = None,
    sort: str = DEFAULT_ACTIVITY_SORT,
    limit: int = Query(default=50, ge=1, le=MAX_ACTIVITY_PAGE),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """One endpoint for both reads the admin panel needs (JM2-1133): one investor's activity
    (`investorRef=`) and the whole platform's feed (omit it), the latter searchable, filterable
    and sortable.

    `investorRef` became optional rather than gaining a second all-investors route: they return
    the same rows in the same shape, differing only by a filter, and a separate route would
    duplicate the search/sort/paging surface and let the two drift.

    `sort` is validated against an allowlist (activity.ACTIVITY_SORTS) and 422s on anything else,
    rather than falling back to the default: silently sorting by something other than what was
    asked for is indistinguishable, from the client's side, from the data being in that order.
    """
    if sort not in ACTIVITY_SORTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unsupported sort '{sort}'; expected one of {', '.join(sorted(ACTIVITY_SORTS))}")
    events, total = await store.search(
        tenant_id, investor_ref=investorRef, q=q, category=category, since=since, until=until,
        sort=sort, limit=limit, offset=offset)
    return {
        "investorRef": investorRef,
        "events": [_activity_json(e) for e in events],
        "total": total, "limit": limit, "offset": offset,
    }


def _intent_signal_response(request_id: str, result: IntentSignalResult | None) -> dict:
    if result is None:
        return {
            "requestId": request_id,
            "error": {"code": "GENERATION_FAILED", "message": "could not draft intent signals"},
        }
    return {"requestId": request_id, "signals": [s.model_dump() for s in result.signals]}


@router.post("/activity/intent-signals")
async def activity_intent_signals(
    tenant_id: str, body: IntentSignalRequest,
    agent: Annotated[Agent | None, Depends(require_worker_caller)],
    store: Annotated[InvestorActivityStore, Depends(get_investor_activity_store)],
    signals: Annotated[IntentSignalStore, Depends(get_intent_signals)],
) -> dict:
    events = await store.list_for_investor(tenant_id, body.investorRef)
    body.activity = aggregate_activity(events)
    config = agent.config if agent is not None else None
    result = await asyncio.to_thread(generate_intent_signals, body, get_provider(), config)
    if result is not None:
        # Persisted so the admin feed can read signals instead of paying to redraft them
        # (JM2-1133). A failed generation (None) leaves the previous set alone: replacing it with
        # nothing would make a transient model failure look like the investor's intent vanished.
        await signals.replace_for_investor(tenant_id, body.investorRef, result.signals)
    return _intent_signal_response(body.requestId, result)


def _stored_signal_json(signal) -> dict:
    return {
        "investorRef": signal.investor_ref, "signal": signal.signal, "strength": signal.strength,
        "evidence": signal.evidence, "category": signal.category,
        "generatedAt": signal.generated_at.isoformat() if signal.generated_at else None,
    }


@router.get("/signals")
async def list_intent_signals(
    tenant_id: str,
    agent: Annotated[Agent | None, Depends(require_worker_caller)],
    activity: Annotated[InvestorActivityStore, Depends(get_investor_activity_store)],
    signals: Annotated[IntentSignalStore, Depends(get_intent_signals)],
    investorRef: str | None = None,
    strength: str | None = Query(default=None, pattern="^(high|medium|low)$"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=MAX_ACTIVITY_PAGE),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Read the intent signals Qiko generated: every investor's (omit `investorRef`) or one
    investor's (JM2-1133).

    A read, not a generation: signals are persisted when they are drafted, so opening the admin
    panel does not spend model budget per row. The one exception is a single investor with no
    stored signals yet but enough activity to support them - drafted once, on demand, then
    stored, so the panel is never blank for an investor who has simply not been processed yet.

    When one investor has no signals AND their activity is too sparse to support any, the
    response says so explicitly (`insufficientActivity: true` plus the thresholds), because an
    empty list alone cannot tell "nothing to say yet" from "something is broken".
    """
    if investorRef is None:
        found, total = await signals.search(tenant_id, strength=strength, q=q, limit=limit,
                                            offset=offset)
        return {
            "signals": [_stored_signal_json(s) for s in found],
            "total": total, "limit": limit, "offset": offset,
        }

    return await _signals_for_one_investor(
        tenant_id, investorRef, agent=agent, activity=activity, signals=signals)


async def _signals_for_one_investor(
    tenant_id: str, investor_ref: str, *, agent, activity, signals,
) -> dict:
    """One investor's signals, drafting them once on demand if they have never been processed.

    Shared by GET /signals?investorRef= and the combined per-user read below, so the two can
    never disagree about what "this investor has no signal" means.
    """
    stored = await signals.list_for_investor(tenant_id, investor_ref)
    if not stored:
        events = await activity.list_for_investor(tenant_id, investor_ref)
        aggregated = aggregate_activity(events)
        if not has_signal_worthy_evidence(aggregated):
            return {
                "investorRef": investor_ref, "signals": [], "insufficientActivity": True,
                "reason": (
                    "not enough repeated engagement to support a signal: needs at least "
                    f"{MIN_PROPERTY_VISITS_FOR_SIGNAL} visits to one property or "
                    f"{MIN_CALCULATOR_VISITS_FOR_SIGNAL} uses of one calculator step"
                ),
                "activityEventCount": len(events),
            }
        request = IntentSignalRequest(
            requestId=f"admin-read-{uuid4()}", investorRef=investor_ref, activity=aggregated)
        config = agent.config if agent is not None else None
        result = await asyncio.to_thread(generate_intent_signals, request, get_provider(), config)
        if result is None:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "could not draft intent signals")
        await signals.replace_for_investor(tenant_id, investor_ref, result.signals)
        stored = await signals.list_for_investor(tenant_id, investor_ref)

    return {
        "investorRef": investor_ref,
        "signals": [_stored_signal_json(s) for s in stored],
        "insufficientActivity": False,
    }


@router.get("/investors/{investor_ref}")
async def get_investor_detail(
    tenant_id: str, investor_ref: str,
    agent: Annotated[Agent | None, Depends(require_worker_caller)],
    activity: Annotated[InvestorActivityStore, Depends(get_investor_activity_store)],
    signals: Annotated[IntentSignalStore, Depends(get_intent_signals)],
    recentLimit: int = Query(default=50, ge=0, le=MAX_ACTIVITY_PAGE),
) -> dict:
    """Everything the admin panel's per-user page shows, in one response (JM2-1136).

    The client's schema is explicit that both blocks - the activity log and the intent signals -
    come from the same Qiko response for that user. Two endpoints would make the page render in
    two stages and let the signals describe a different moment than the log shown beside them.

    `activity.screens`, `activity.properties` and `activity.calculatorSteps` are the counted view
    the page actually displays. Counts, not raw rows: "viewed Marina Heights 5 times" is the
    behaviour an admin reads, and it is the same aggregation the signal generation is grounded
    in, so the evidence on a signal card always reconciles with the numbers next to it.

    `activity.recent` carries the underlying events for the log panel, newest first. Pass
    `recentLimit=0` to skip them when only the counts are needed.
    """
    events = await activity.list_for_investor(tenant_id, investor_ref)
    aggregated = aggregate_activity(events)
    recent = sorted(
        events, key=lambda e: e.occurred_at or datetime.min.replace(tzinfo=UTC), reverse=True,
    )[:recentLimit]
    signal_block = await _signals_for_one_investor(
        tenant_id, investor_ref, agent=agent, activity=activity, signals=signals)

    return {
        "investorRef": investor_ref,
        "activity": {
            "screens": [
                {"label": label, "visitCount": count}
                for label, count in sorted(aggregated["screens"].items(),
                                           key=lambda kv: (-kv[1], kv[0]))
            ],
            "properties": sorted(aggregated["properties"],
                                 key=lambda p: (-p["visitCount"], p["propertyName"])),
            "calculatorSteps": [
                {"step": step, "visitCount": count}
                for step, count in sorted(aggregated["calculatorSteps"].items(),
                                          key=lambda kv: (-kv[1], kv[0]))
            ],
            "totalEvents": len(events),
            "recent": [_activity_json(e) for e in recent],
        },
        "signals": signal_block["signals"],
        "insufficientActivity": signal_block["insufficientActivity"],
        **({"reason": signal_block["reason"],
            "activityEventCount": signal_block["activityEventCount"]}
           if signal_block.get("insufficientActivity") else {}),
    }


def _insight_response(request_id: str, result: PropertyInsightResult | None) -> dict:
    if result is None:
        return {
            "requestId": request_id,
            "error": {"code": "GENERATION_FAILED", "message": "could not draft a grounded insight"},
        }
    return {"requestId": request_id, "summary": result.summary, "groundedIn": result.groundedIn}
