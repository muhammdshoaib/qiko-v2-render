"""CRM / Sales Pipeline HTTP API (tenant-scoped). Every worker gets this -- not specific to any
one worker's industry/vertical."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_agents, get_crm, require_role, resolve_tenant_worker
from app.modules.ai.gateway import get_provider
from app.modules.crm.service import CrmError
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/crm", tags=["crm"])


async def _contact_guard(request: Request, tenant: str, contact_id: str, svc):
    contact = await svc.contacts.get(tenant, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    _worker, recheck = await resolve_tenant_worker(request, tenant, contact.agent_id)
    return contact, recheck


async def _action_guard(request: Request, tenant: str, action_id: str, svc):
    action = await svc.get_action(tenant, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    contact, recheck = await _contact_guard(request, tenant, action.contact_id, svc)
    return action, contact, recheck


def _contact_out(c) -> dict:
    return {
        "id": c.id, "agentId": c.agent_id, "conversationId": c.conversation_id, "name": c.name,
        "email": c.email, "phone": c.phone, "status": c.status, "estimatedValue": c.estimated_value,
        "currency": c.currency, "aiSummary": c.ai_summary, "sentiment": c.sentiment,
        "keyTopics": c.key_topics, "createdAt": c.created_at, "updatedAt": c.updated_at,
    }


def _action_out(a) -> dict:
    return {
        "id": a.id, "contactId": a.contact_id, "actionType": a.action_type, "title": a.title,
        "description": a.description, "priority": a.priority, "status": a.status, "createdAt": a.created_at,
    }


@router.get("/{agent_id}")
async def get_pipeline(agent_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_crm)) -> dict:
    result = await svc.list_pipeline(tenant, agent_id)
    return {
        "contacts": [_contact_out(c) for c in result["contacts"]], "total": result["total"],
        "dashboard": {"statusBreakdown": result["dashboard"]["status_breakdown"]},
    }


@router.get("/contacts/{contact_id}")
async def get_contact_detail(contact_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_crm)) -> dict:
    try:
        detail = await svc.get_detail(tenant, contact_id)
    except CrmError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {
        "contact": _contact_out(detail["contact"]), "timeline": detail["timeline"],
        "actions": [_action_out(a) for a in detail["actions"]], "bookings": detail["bookings"],
        "stats": {"messageCount": detail["stats"]["message_count"],
                  "voiceCallCount": detail["stats"]["voice_call_count"],
                  "emailCount": detail["stats"]["email_count"]},
    }


class UpdateContactBody(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None
    estimated_value: int | None = None


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: UpdateContactBody, request: Request,
                         tenant: str = Depends(authed_tenant),
                         _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_crm)) -> dict:
    _contact, recheck = await _contact_guard(request, tenant, contact_id, svc)
    try:
        contact = await svc.update_contact(tenant, contact_id, name=body.name, email=body.email,
                                           phone=body.phone, status=body.status,
                                           estimated_value=body.estimated_value)
    except CrmError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await recheck()
    return _contact_out(contact)


@router.post("/contacts/{contact_id}/summary")
async def generate_summary(contact_id: str, request: Request,
                           tenant: str = Depends(authed_tenant),
                           _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_crm)) -> dict:
    _contact, recheck = await _contact_guard(request, tenant, contact_id, svc)
    try:
        contact = await svc.generate_summary(
            tenant, contact_id, get_provider(), recheck_worker=recheck)
    except CrmError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await recheck()
    return _contact_out(contact)


class AddActionBody(BaseModel):
    title: str = Field(min_length=1)
    action_type: str = "custom"
    description: str = ""
    priority: str = "normal"


@router.post("/contacts/{contact_id}/actions")
async def add_action(contact_id: str, body: AddActionBody, request: Request,
                     tenant: str = Depends(authed_tenant),
                     _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_crm)) -> dict:
    _contact, recheck = await _contact_guard(request, tenant, contact_id, svc)
    try:
        action = await svc.add_action(tenant, contact_id, title=body.title, action_type=body.action_type,
                                      description=body.description, priority=body.priority)
    except CrmError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await recheck()
    return _action_out(action)


class UpdateActionBody(BaseModel):
    status: str = Field(min_length=1)


@router.patch("/actions/{action_id}")
async def update_action(action_id: str, body: UpdateActionBody, request: Request,
                        tenant: str = Depends(authed_tenant),
                        _role: dict = Depends(require_role(Role.editor)), svc=Depends(get_crm)) -> dict:
    _action, _contact, recheck = await _action_guard(request, tenant, action_id, svc)
    try:
        action = await svc.update_action_status(tenant, action_id, body.status)
    except CrmError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await recheck()
    return _action_out(action)


@router.post("/contacts/{contact_id}/sync-salesforce")
async def sync_to_salesforce(contact_id: str, request: Request,
                             tenant: str = Depends(authed_tenant),
                             _role: dict = Depends(require_role(Role.editor)),
                             svc=Depends(get_crm), agents=Depends(get_agents)) -> dict:
    """Push a pipeline contact to Salesforce as a Lead, using whichever worker (agent) this
    contact belongs to -- the Salesforce connection lives on the agent, same place as Vapi/
    Calendly, so this works for any worker with credentials configured, not just one client's."""
    import asyncio

    from app.core.crypto import decrypt
    from app.integrations.clients import SalesforceAuthError, SalesforceClient

    try:
        detail = await svc.get_detail(tenant, contact_id)
    except CrmError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    contact = detail["contact"]
    _persisted, recheck = await _contact_guard(request, tenant, contact_id, svc)

    agent = await agents.get(tenant, contact.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="the worker this contact belongs to no longer exists")
    cfg = agent.config
    if not cfg.get("salesforce_credentials_added"):
        raise HTTPException(status_code=422, detail="this worker has no Salesforce connection configured")

    client = SalesforceClient(client_id=cfg["salesforce_client_id"],
                              client_secret=decrypt(cfg["salesforce_client_secret_encrypted"]),
                              instance_url=cfg["salesforce_instance_url"])
    try:
        try:
            result = await asyncio.to_thread(
                client.create_lead, last_name=contact.name or "Unknown",
                company=f"{contact.name or 'Unknown'} (via {agent.name})",
                email=contact.email, phone=contact.phone,
                description=contact.ai_summary)
        finally:
            await recheck()
    except SalesforceAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"synced": True, "salesforce_id": result.get("id")}
