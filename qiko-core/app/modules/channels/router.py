"""Channels HTTP API: WhatsApp (Meta Graph) webhook verify + inbound receive."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import (
    authed_tenant,
    get_calendly,
    get_channel_sessions,
    get_clickup,
    get_gmail,
    get_slack,
    get_slack_links,
    get_slack_oauth,
    get_teams_notifier,
    get_whatsapp,
    require_role,
)
from app.modules.channels.teams_integration import TeamsWebhookError
from app.modules.channels.webhooks import verify_hmac_signature
from app.modules.channels.whatsapp import verify_webhook
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/channels", tags=["channels"])
_editor = Depends(require_role(Role.editor))


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
    body = await request.body()
    s = get_settings()
    if s.whatsapp_app_secret:
        if not verify_hmac_signature(s.whatsapp_app_secret, body, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="invalid signature")
    elif not s.debug:  # fail closed outside dev: refuse unverifiable webhooks
        raise HTTPException(status_code=403, detail="webhook signature secret not configured")
    messages = adapter.handle_inbound(json.loads(body or b"{}"))
    return {"processed": [m.message_id for m in messages]}


# --- outbound sends (authenticated, editor) ---
class SendText(BaseModel):
    to: str = Field(min_length=1)
    text: str = Field(min_length=1)


@router.post("/whatsapp/send")
def whatsapp_send(body: SendText, _t: str = Depends(authed_tenant), _r: dict = _editor, adapter=Depends(get_whatsapp)) -> dict:
    return adapter.reply(body.to, body.text)


class GmailSend(BaseModel):
    to: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


@router.post("/gmail/send")
def gmail_send(body: GmailSend, _t: str = Depends(authed_tenant), _r: dict = _editor, gmail=Depends(get_gmail)) -> dict:
    return gmail.send(body.to, body.subject, body.body)


class SlackSend(BaseModel):
    channel: str = Field(min_length=1)
    text: str = Field(min_length=1)


@router.post("/slack/send")
def slack_send(body: SlackSend, _t: str = Depends(authed_tenant), _r: dict = _editor, slack=Depends(get_slack)) -> dict:
    return slack.send_message(body.channel, body.text)


class ClickUpTask(BaseModel):
    list_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""


@router.post("/clickup/task")
def clickup_task(body: ClickUpTask, _t: str = Depends(authed_tenant), _r: dict = _editor, clickup=Depends(get_clickup)) -> dict:
    return clickup.create_task(body.list_id, body.name, body.description)


# --- Calendly ---
@router.get("/calendly/slots")
def calendly_slots(event_type: str, _t: str = Depends(authed_tenant), cal=Depends(get_calendly)) -> dict:
    return {"slots": cal.available_slots(event_type)}


class CalendlyBook(BaseModel):
    event_type: str = Field(min_length=1)
    invitee_email: str = Field(min_length=3)
    start: str = Field(min_length=1)


@router.post("/calendly/book")
def calendly_book(body: CalendlyBook, _t: str = Depends(authed_tenant), cal=Depends(get_calendly)) -> dict:
    return cal.create_booking(body.event_type, body.invitee_email, body.start)


# --- Slack OAuth (public redirects) ---
@router.get("/slack/install")
def slack_install(state: str = "qiko", oauth=Depends(get_slack_oauth)) -> dict:
    return {"url": oauth.install_url(state)}


@router.get("/slack/callback")
def slack_callback(code: str, oauth=Depends(get_slack_oauth)) -> dict:
    inst = oauth.exchange_code(code)
    return {"team_id": inst.team_id, "installed": True}


class SlackLink(BaseModel):
    team_id: str = Field(min_length=1)
    slack_user_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)


@router.post("/slack/link")
def slack_link(body: SlackLink, _t: str = Depends(authed_tenant), links=Depends(get_slack_links)) -> dict:
    links.link(body.team_id, body.slack_user_id, body.worker_id)
    return {"linked": True}


# --- channel sessions ---
class WorkerSel(BaseModel):
    worker: str = Field(min_length=1)


@router.post("/sessions/{external_id}/worker")
def session_select_worker(external_id: str, body: WorkerSel, tenant: str = Depends(authed_tenant),
                          sessions=Depends(get_channel_sessions)) -> dict:
    sessions.select_worker(tenant, external_id, body.worker)
    return {"external_id": external_id, "selected_worker": body.worker}


@router.get("/sessions/{external_id}")
def session_get(external_id: str, tenant: str = Depends(authed_tenant), sessions=Depends(get_channel_sessions)) -> dict:
    s = sessions.get(tenant, external_id)
    if s is None:
        raise HTTPException(status_code=404, detail="no session")
    return {"external_id": external_id, "selected_worker": s.selected_worker, "reply_mode": s.reply_mode}


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
async def teams_webhook_test(tenant: str = Depends(authed_tenant), _r: dict = _editor,
                             notifier=Depends(get_teams_notifier)) -> dict:
    try:
        await notifier.send_test(tenant)
    except TeamsWebhookError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # webhook URL rejected by Teams, network error, ...
        raise HTTPException(status_code=502, detail=f"could not reach Teams: {e}") from e
    return {"sent": True}
