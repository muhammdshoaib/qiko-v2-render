"""Channels HTTP API: WhatsApp (Meta Graph) webhook verify + inbound receive."""
from __future__ import annotations

import asyncio
import html
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.core.deps import (
    WorkerUnavailable,
    authed_tenant,
    get_agents,
    get_channel_sessions,
    get_interakt,
    get_interakt_idempotency,
    get_jm_backend,
    get_slack_links,
    get_slack_oauth,
    get_teams_notifier,
    get_whatsapp,
    require_role,
    resolve_tenant_worker,
    stored_credential,
)
from app.modules.channels.teams_integration import TeamsWebhookError
from app.modules.channels.webhooks import verify_hmac_signature
from app.modules.channels.whatsapp import verify_webhook
from app.modules.channels.interakt import ReplyMode, parse_inbound
from app.modules.identity.rbac import Role
from app.modules.joseph_mews.conversation import advance_turn
from app.modules.joseph_mews.extraction import extract_qualification
from app.modules.joseph_mews.jm_backend_client import HandoffPacket, JmBackendError
from app.modules.joseph_mews.worker import joseph_mews_worker_config
from app.modules.workers.worker import build_worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"])
_editor = Depends(require_role(Role.editor))


async def _external_call(recheck, function, *args):
    try:
        return await asyncio.to_thread(function, *args)
    finally:
        await recheck()


def _get_slack_events(request: Request):
    return request.app.state.slack_events


@router.post("/slack/webhook")
async def slack_webhook(request: Request,
                        x_slack_signature: str = Header(default=""),
                        x_slack_request_timestamp: str = Header(default=""),
                        handler=Depends(_get_slack_events)) -> dict:
    """Slack Events API callback. Public, signature-verified, no tenant cookie.

    Processes `url_verification`, `message` and `app_mention`. Messages from public channels are
    stored in the per-tenant buffer for the digest worker only when the worker has explicitly
    watched that channel via the source-connection UI.

    The 403 body is deliberately generic. The reason (bad signature vs unconfigured secret) is a
    fact about server configuration and belongs in the log, not in a reply to an unauthenticated
    caller.
    """
    body = await request.body()
    s = get_settings()
    if s.slack_signing_secret:
        if not handler.verify(x_slack_request_timestamp, body, x_slack_signature):
            logger.warning("slack webhook rejected: signature invalid, stale or missing",
                           extra={"source": "channels.slack"})
            raise HTTPException(status_code=403, detail="forbidden")
    elif not s.debug:  # fail closed outside dev: refuse unverifiable webhooks
        logger.error("slack webhook rejected: SLACK_SIGNING_SECRET is not configured",
                     extra={"source": "channels.slack"})
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc

    return await handler.handle(payload)


@router.get("/whatsapp/webhook")
def whatsapp_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    challenge = verify_webhook(hub_mode, hub_verify_token, hub_challenge,
                              expected_token=get_settings().whatsapp_verify_token)
    if challenge is None:
        raise HTTPException(status_code=403, detail="verification failed")
    return int(challenge) if challenge.isdigit() else challenge


@router.post("/whatsapp/webhook")
async def whatsapp_inbound(request: Request, x_hub_signature_256: str = Header(default=""),
                           adapter=Depends(get_whatsapp)) -> dict:
    """Inbound WhatsApp webhook. DISABLED by default, and honest about why.

    The adapter only de-duplicates and returns message ids: it never resolves a worker, never calls
    worker.answer and never replies, despite a docstring that claimed inbound text was routed through
    agentcore. Meta reads a 200 as "delivered and handled" and will not retry, so every customer
    message was being silently dropped while the platform reported success.

    Returning 501 rather than removing the route keeps the webhook URL registered and gives an operator
    an unambiguous signal, instead of a 404 that looks like a misconfiguration. Set
    CHANNELS_INBOUND_ENABLED=true only once the routing is actually implemented.
    """
    body = await request.body()
    s = get_settings()
    if not s.channels_inbound_enabled:
        raise HTTPException(status_code=501, detail="inbound channel routing is not implemented")
    if s.whatsapp_app_secret:
        if not verify_hmac_signature(s.whatsapp_app_secret, body, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="invalid signature")
    elif not s.debug:  # fail closed outside dev: refuse unverifiable webhooks
        raise HTTPException(status_code=403, detail="webhook signature secret not configured")
    messages = adapter.handle_inbound(json.loads(body or b"{}"))
    return {"processed": [m.message_id for m in messages]}


@router.post("/interakt/webhook")
async def interakt_inbound(
    request: Request,
    interakt_signature: str = Header(default="", alias="Interakt-Signature"),
    gateway=Depends(get_interakt),
    idempotency=Depends(get_interakt_idempotency),
    jm_backend=Depends(get_jm_backend),
) -> dict:
    """Inbound Interakt webhook for the joseph-mews tenant's Joe agent.

    Same DISABLED-by-default honesty as whatsapp_inbound above (CHANNELS_INBOUND_ENABLED), for the
    same reason: acking 200 for a message nothing actually answers is worse than an explicit 501.

    Interakt has ~3 seconds to get a 200 back (JM2-1024 research); worker.answer runs a retrieval
    embedding and a generation call, comfortably over that budget, so this must not block the ack
    on it. There is no task queue wired for this yet (JM2-1025 tracks moving idempotency to Redis
    for the same reason), so this is currently synchronous for correctness's sake, not throughput -
    tracked as a known follow-up rather than silently accepted.
    """
    body = await request.body()
    s = get_settings()
    if not s.channels_inbound_enabled:
        raise HTTPException(status_code=501, detail="inbound channel routing is not implemented")
    if s.interakt_webhook_secret:
        if not verify_hmac_signature(s.interakt_webhook_secret, body, interakt_signature):
            raise HTTPException(status_code=403, detail="invalid signature")
    elif not s.debug:
        raise HTTPException(status_code=403, detail="webhook signature secret not configured")

    parsed = parse_inbound(json.loads(body or b"{}"))
    if parsed is None:
        return {"processed": []}
    if idempotency.is_duplicate(parsed.message_id):
        return {"processed": []}

    worker = build_worker(
        joseph_mews_worker_config(),
        knowledge=request.app.state.knowledge,
        cost_guard=getattr(request.app.state, "cost_guard", None),
    )

    # jm-backend owns conversation history (JM2-1023); best-effort here, since a lead's message
    # must still get an answer even if jm-backend is briefly unavailable, just without history or
    # qualification-based escalation for this one turn rather than dropping it.
    history_context: list[str] | None = None
    qualification = None
    try:
        state = jm_backend.record_turn(
            parsed.phone_number, "customer", parsed.text, interakt_message_id=parsed.message_id,
        )
        history_context = [f"{turn.role}: {turn.text}" for turn in state.history]
        qualification = extract_qualification(
            "\n".join(history_context), worker.agent.generator.provider,
        )
    except JmBackendError:
        logger.warning("jm-backend unavailable for %s, answering without history", parsed.phone_number)

    reply = await advance_turn(
        worker, parsed.phone_number, parsed.text,
        history_context=history_context, qualification=qualification,
    )
    outcome = gateway.send(parsed.phone_number, reply)

    handoff = None
    if reply.reply_mode is ReplyMode.handoff:
        # JM2-1031: only a genuine handoff carries a packet - draft_for_agent/template turns
        # have no reason_code/summary/suggested_next_action to send, and jm-backend's own
        # HandoffPacket schema requires all three.
        handoff = HandoffPacket(
            reason_code=reply.handoff_reason_code or "unspecified",
            summary=reply.handoff_reason or "Joe handed this conversation off for human review.",
            suggested_next_action=reply.handoff_suggested_next_action or "Review the conversation and reply manually.",
            priority=reply.handoff_priority or "medium",
            extracted_traits=reply.handoff_extracted_traits or {},
        )

    try:
        jm_backend.record_turn(
            parsed.phone_number, "joe",
            reply.draft_text or reply.handoff_reason or reply.reply_mode.value,
            template_used=reply.template_name, handoff=handoff,
        )
    except JmBackendError:
        logger.warning("jm-backend unavailable for %s, Joe's turn was not persisted", parsed.phone_number)

    return {"processed": [parsed.message_id], "replyMode": reply.reply_mode.value, "outcome": outcome}


# --- outbound sends (authenticated, editor) ---
class SendText(BaseModel):
    to: str = Field(min_length=1)
    text: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)


@router.post("/whatsapp/send")
async def whatsapp_send(body: SendText, request: Request,
                        tenant: str = Depends(authed_tenant), _role: dict = _editor,
                        adapter=Depends(get_whatsapp)) -> dict:
    _worker, recheck = await resolve_tenant_worker(request, tenant, body.worker_id)
    return await _external_call(recheck, adapter.reply, body.to, body.text)


class GmailSend(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)

    @field_validator("to")
    @classmethod
    def _single_clean_recipient(cls, v: str) -> str:
        """One recipient only. smtplib derives the envelope RCPT TO from the To header, so a comma or
        an embedded newline would silently fan one API call out to many recipients."""
        v = v.strip()
        if any(ch in v for ch in (",", ";", "\r", "\n")) or "@" not in v.strip("@"):
            raise ValueError("to must be a single email address")
        return v


def _tenant_gmail(cfg: dict):
    """Build a Gmail sender from THIS worker's own address + App Password (no shared Qiko mailbox)."""
    from app.integrations.clients import GmailSmtpClient

    password = stored_credential(cfg, flag="gmail_credentials_added",
                                 key="gmail_app_password_encrypted", label="Gmail")
    return GmailSmtpClient(address=cfg.get("gmail_address") or "", app_password=password)


@router.post("/gmail/send")
async def gmail_send(body: GmailSend, request: Request,
                     tenant: str = Depends(authed_tenant), _role: dict = _editor,
                     agents=Depends(get_agents)) -> dict:
    from app.integrations.clients import GmailSmtpError

    cfg = await _worker_config(agents, tenant, body.worker_id)
    gmail = _tenant_gmail(cfg)
    _worker, recheck = await resolve_tenant_worker(request, tenant, body.worker_id)
    try:
        return await _external_call(recheck, gmail.send, body.to, body.subject, body.body)
    except GmailSmtpError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


class SlackSend(BaseModel):
    # Two supported shapes: (a) worker_id -> the worker's own stored bot token, or (b) the linked
    # workspace flow (team_id + slack_user_id -> that installation's bot token).
    worker_id: str = Field(default="", max_length=128)
    team_id: str = Field(default="", max_length=64)
    slack_user_id: str = Field(default="", max_length=64)
    channel: str = Field(default="", max_length=80)
    text: str = Field(min_length=1)


@router.post("/slack/send")
async def slack_send(body: SlackSend, request: Request,
                     tenant: str = Depends(authed_tenant), _role: dict = _editor,
                     agents=Depends(get_agents),
                     links=Depends(get_slack_links), oauth=Depends(get_slack_oauth)) -> dict:
    from app.integrations.clients import SlackAuthError, SlackClient

    if body.worker_id:
        cfg = await _worker_config(agents, tenant, body.worker_id)
        token = stored_credential(cfg, flag="slack_credentials_added",
                                  key="slack_bot_token_encrypted", label="Slack")
        channel = body.channel or cfg.get("slack_default_channel") or ""
        if not channel:
            raise HTTPException(status_code=422, detail="no Slack channel configured for this worker")
        worker_id = body.worker_id
    else:
        if not (body.team_id and body.slack_user_id and body.channel):
            raise HTTPException(status_code=422, detail="provide worker_id, or team_id + slack_user_id + channel")
        worker_id = links.resolve(tenant, body.team_id, body.slack_user_id)
        if worker_id is None:
            raise HTTPException(status_code=404, detail="Slack worker link not found")
        # Synchronous store (app/db/sync_stores.py) called from an async handler. `tenant` is
        # passed BY KEYWORD: fetch's second positional parameter is enterprise_id, so a positional
        # call here would silently look up the wrong installation.
        installation = await asyncio.to_thread(oauth.store.fetch, body.team_id, tenant=tenant)
        if installation is None or installation.worker_id != worker_id:
            raise HTTPException(status_code=404, detail="Slack installation not found")
        token, channel = installation.bot_token, body.channel

    _worker, recheck = await resolve_tenant_worker(request, tenant, worker_id)
    slack = SlackClient(bot_token=token)
    try:
        return await _external_call(recheck, slack.send_message, channel, body.text)
    except SlackAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


class ClickUpTask(BaseModel):
    list_id: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")  # else the worker default
    name: str = Field(min_length=1)
    description: str = ""
    worker_id: str = Field(min_length=1)


async def _worker_config(agents, tenant: str, worker_id: str) -> dict:
    agent = await agents.get(tenant, worker_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="worker not found")
    return agent.config


def _tenant_clickup(cfg: dict):
    """Build a ClickUp client from THIS worker's own stored token. There is no global fallback on
    purpose: sending a customer's task into Qiko's own ClickUp would be worse than a clear 422."""
    from app.integrations.clients import ClickUpClient

    token = stored_credential(cfg, flag="clickup_credentials_added",
                              key="clickup_api_token_encrypted", label="ClickUp")
    return ClickUpClient(api_token=token)


def _tenant_calendly(cfg: dict):
    """Build a Calendly client from THIS worker's own stored token (no global fallback -- see above)."""
    from app.integrations.clients import CalendlyClient

    token = stored_credential(cfg, flag="calendly_credentials_added",
                              key="calendly_token_encrypted", label="Calendly")
    return CalendlyClient(token=token)


@router.post("/clickup/task")
async def clickup_task(body: ClickUpTask, request: Request,
                       tenant: str = Depends(authed_tenant), _role: dict = _editor,
                       agents=Depends(get_agents)) -> dict:
    cfg = await _worker_config(agents, tenant, body.worker_id)
    clickup = _tenant_clickup(cfg)
    _worker, recheck = await resolve_tenant_worker(request, tenant, body.worker_id)
    list_id = body.list_id or cfg.get("clickup_default_list_id") or ""
    if not list_id:
        raise HTTPException(status_code=422, detail="no ClickUp list configured for this worker")
    return await _external_call(
        recheck, clickup.create_task, list_id, body.name, body.description)


# --- Calendly ---
@router.get("/calendly/slots")
async def calendly_slots(worker_id: str, request: Request, event_type: str = "",
                         tenant: str = Depends(authed_tenant), agents=Depends(get_agents)) -> dict:
    cfg = await _worker_config(agents, tenant, worker_id)
    cal = _tenant_calendly(cfg)
    resolved = event_type or cfg.get("calendly_event_type") or ""
    if not resolved:
        raise HTTPException(status_code=422, detail="no Calendly event type configured for this worker")
    _worker, recheck = await resolve_tenant_worker(request, tenant, worker_id)
    slots = await _external_call(recheck, cal.available_slots, resolved)
    return {"slots": slots}


class CalendlyBook(BaseModel):
    event_type: str = Field(min_length=1)
    invitee_email: str = Field(min_length=3)
    start: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)


@router.post("/calendly/book")
async def calendly_book(body: CalendlyBook, request: Request,
                        tenant: str = Depends(authed_tenant), _role: dict = _editor,
                        agents=Depends(get_agents)) -> dict:
    cfg = await _worker_config(agents, tenant, body.worker_id)
    cal = _tenant_calendly(cfg)
    _worker, recheck = await resolve_tenant_worker(request, tenant, body.worker_id)
    return await _external_call(
        recheck, cal.create_booking, body.event_type, body.invitee_email, body.start)


# --- Slack OAuth (public redirects) ---
@router.get("/slack/install")
async def slack_install(worker_id: str, request: Request,
                        tenant: str = Depends(authed_tenant),
                        claims: dict = Depends(require_role(Role.editor)),
                        oauth=Depends(get_slack_oauth)) -> dict:
    _worker, recheck = await resolve_tenant_worker(request, tenant, worker_id)
    result = oauth.create_install(tenant, worker_id, claims.get("sub"))
    await recheck()
    return result


@router.get("/slack/callback")
async def slack_callback(code: str, state: str, request: Request,
                         oauth=Depends(get_slack_oauth),
                         agents=Depends(get_agents)) -> HTMLResponse:
    async def recheck(tenant: str, worker_id: str) -> None:
        _worker, check = await resolve_tenant_worker(request, tenant, worker_id)
        await check()

    settings = get_settings()
    try:
        installation = await oauth.complete_install(
            code, state, recheck_worker=recheck)
    except Exception:
        return _slack_oauth_html(
            connected=False, detail="invalid Slack OAuth callback", settings=settings)

    await agents.update_config(
        installation.tenant, installation.worker_id,
        {"slack_watched_channels": [], "slack_team_id": installation.team_id})
    return _slack_oauth_html(
        connected=True, worker_id=installation.worker_id, detail=installation.team_id, settings=settings)


def _slack_oauth_html(
    *, connected: bool, detail: str, settings, worker_id: str | None = None,
) -> HTMLResponse:
    """Return a self-closing popup page for Slack OAuth, or redirect if opened directly."""
    base = (settings.frontend_url or "").rstrip("/") or "/"
    redirect_url = f"{base}/workers/{worker_id}?tab=Sources" if worker_id else base
    target_origin = base if base != "/" else "*"
    message_type = "slack-connected" if connected else "slack-error"
    safe_detail = html.escape(detail)
    body = f"""<html><head><title>{"Slack connected" if connected else "Slack connection failed"}</title></head><body>
<p>{"Slack connected. You can close this window." if connected else safe_detail}</p>
<script>
if (window.opener) {{ window.opener.postMessage({{ type: {json.dumps(message_type)}, detail: {json.dumps(detail)} }}, {json.dumps(target_origin)}); window.close(); }}
else {{ window.location.href = {json.dumps(redirect_url)}; }}
</script>
</body></html>"""
    return HTMLResponse(content=body)


class SlackLink(BaseModel):
    team_id: str = Field(min_length=1)
    slack_user_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)


@router.post("/slack/link")
async def slack_link(body: SlackLink, request: Request,
                     tenant: str = Depends(authed_tenant), _role: dict = _editor,
                     links=Depends(get_slack_links)) -> dict:
    _worker, recheck = await resolve_tenant_worker(request, tenant, body.worker_id)
    links.link(tenant, body.team_id, body.slack_user_id, body.worker_id)
    await recheck()
    return {"linked": True}


# --- channel sessions ---
class WorkerSel(BaseModel):
    worker: str = Field(min_length=1)


@router.post("/sessions/{external_id}/worker")
async def session_select_worker(external_id: str, body: WorkerSel, request: Request,
                                tenant: str = Depends(authed_tenant), _role: dict = _editor,
                                sessions=Depends(get_channel_sessions)) -> dict:
    _worker, recheck = await resolve_tenant_worker(request, tenant, body.worker)
    sessions.select_worker(tenant, external_id, body.worker)
    await recheck()
    return {"external_id": external_id, "selected_worker": body.worker}


@router.get("/sessions/{external_id}")
async def session_get(external_id: str, request: Request,
                      tenant: str = Depends(authed_tenant),
                      sessions=Depends(get_channel_sessions)) -> dict:
    session = sessions.get(tenant, external_id)
    if session is None:
        raise HTTPException(status_code=404, detail="no session")
    if session.selected_worker:
        _worker, recheck = await resolve_tenant_worker(
            request, tenant, session.selected_worker)
        await recheck()
    return {"external_id": external_id, "selected_worker": session.selected_worker,
            "reply_mode": session.reply_mode}


# --- Microsoft Teams Integration (notifications via a per-tenant Incoming Webhook) ---
class TeamsWebhookBody(BaseModel):
    webhook_url: str = Field(min_length=8)


@router.get("/teams/webhook")
async def teams_webhook_status(tenant: str = Depends(authed_tenant), notifier=Depends(get_teams_notifier)) -> dict:
    return await notifier.status(tenant)


@router.put("/teams/webhook")
async def teams_webhook_connect(body: TeamsWebhookBody, tenant: str = Depends(authed_tenant),
                                _r: dict = _editor, notifier=Depends(get_teams_notifier)) -> dict:
    """Paste the URL from Teams > channel > Connectors > Incoming Webhook. Stored encrypted --
    never returned again, same as the Vapi API key (see agents/router.py)."""
    try:
        await notifier.connect(tenant, body.webhook_url)
    except TeamsWebhookError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return await notifier.status(tenant)


@router.delete("/teams/webhook")
async def teams_webhook_disconnect(tenant: str = Depends(authed_tenant), _r: dict = _editor,
                                   notifier=Depends(get_teams_notifier)) -> dict:
    await notifier.disconnect(tenant)
    return {"connected": False}


@router.post("/teams/test")
async def teams_webhook_test(body: WorkerSel, request: Request,
                             tenant: str = Depends(authed_tenant), _role: dict = _editor,
                             notifier=Depends(get_teams_notifier)) -> dict:
    _worker, recheck = await resolve_tenant_worker(request, tenant, body.worker)
    try:
        try:
            await notifier.send_test(tenant)
        finally:
            await recheck()
    except WorkerUnavailable:
        raise
    except TeamsWebhookError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # webhook URL rejected by Teams, network error, ...
        raise HTTPException(status_code=502, detail=f"could not reach Teams: {e}") from e
    return {"sent": True}
