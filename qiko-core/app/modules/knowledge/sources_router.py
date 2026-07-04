"""Worker knowledge-sources HTTP API (tenant-scoped, editor role).

Structured sources (behaviors/FAQs/policies/websites/persona) are rendered to text and ingested
into the vector store under deterministic doc ids, so the worker's agentcore answers stay grounded
in them. This is a typed layer over KnowledgeService (agentic-first: sources feed the grounding).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_sources, require_role
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/agents/{agent_id}/sources", tags=["knowledge-sources"])
_editor = Depends(require_role(Role.editor))


class BehaviorBody(BaseModel):
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class FaqBody(BaseModel):
    source_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class PolicyBody(BaseModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)


class WebsiteBody(BaseModel):
    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    details: str = ""


class PersonaBody(BaseModel):
    fields: dict


@router.post("/behaviors")
async def add_behavior(agent_id: str, body: BehaviorBody, tenant: str = Depends(authed_tenant),
                       _r: dict = _editor, svc=Depends(get_sources)) -> dict:
    return {"doc_id": await svc.add_behavior(tenant, agent_id, body.source_id, body.text)}


@router.post("/faqs")
async def add_faq(agent_id: str, body: FaqBody, tenant: str = Depends(authed_tenant),
                  _r: dict = _editor, svc=Depends(get_sources)) -> dict:
    return {"doc_id": await svc.add_faq(tenant, agent_id, body.source_id, body.question, body.answer)}


@router.post("/policies")
async def add_policy(agent_id: str, body: PolicyBody, tenant: str = Depends(authed_tenant),
                     _r: dict = _editor, svc=Depends(get_sources)) -> dict:
    return {"doc_id": await svc.add_policy(tenant, agent_id, body.source_id, body.title, body.body)}


@router.post("/websites")
async def add_website(agent_id: str, body: WebsiteBody, tenant: str = Depends(authed_tenant),
                      _r: dict = _editor, svc=Depends(get_sources)) -> dict:
    return {"doc_id": await svc.add_website(tenant, agent_id, body.source_id, body.name, body.url, body.details)}


@router.put("/persona")
async def set_persona(agent_id: str, body: PersonaBody, tenant: str = Depends(authed_tenant),
                      _r: dict = _editor, svc=Depends(get_sources)) -> dict:
    return {"doc_id": await svc.set_persona(tenant, agent_id, body.fields)}


@router.delete("/{kind}/{source_id}")
async def delete_source(agent_id: str, kind: str, source_id: str, tenant: str = Depends(authed_tenant),
                        _r: dict = _editor, svc=Depends(get_sources)) -> dict:
    return {"removed": await svc.delete_source(tenant, agent_id, kind, source_id)}
