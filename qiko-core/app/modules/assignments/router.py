"""Section-assignment HTTP API (tenant-scoped): assign RFP sections/questions to team members,
track status, and roll it up into a per-member dashboard."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import (
    authed_tenant,
    current_claims,
    get_assignments,
    get_pack_tree,
    get_rfp_packs,
    get_user_store,
    require_role,
    resolve_tenant_worker,
)
from app.modules.assignments.service import (
    Assignment,
    AssignmentError,
    AssignmentNotFound,
    QuestionAssignBody,
    SectionAssignBody,
)
from app.modules.email.sender import get_email_sender
from app.modules.identity.rbac import Role
from app.modules.rfp.service import RfpPackNotFound
from app.modules.rfp.tree import PackSectionNotFound

router = APIRouter(prefix="/assignments", tags=["assignments"])
_admin = Depends(require_role(Role.admin))


async def _resolve_pack(request: Request, tenant: str, pack_id: str, packs):
    try:
        pack = await packs.get(tenant, pack_id)
    except RfpPackNotFound as e:
        raise HTTPException(status_code=404, detail="RFP pack not found") from e
    _worker, recheck = await resolve_tenant_worker(request, tenant, pack.agent_id)
    return pack, recheck


async def _get_assignment(svc, tenant: str, assignment_id: str) -> Assignment:
    assignment = await svc.get(tenant, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    return assignment


async def _resolve_assignment_pack(request, tenant, assignment, packs, tree):
    pack, recheck = await _resolve_pack(request, tenant, assignment.pack_id, packs)
    if assignment.agent_id != pack.agent_id:
        raise HTTPException(status_code=404, detail="assignment not found")
    if assignment.section_id is not None:
        try:
            await tree.get_section_for_pack(tenant, assignment.pack_id, assignment.section_id)
        except PackSectionNotFound as e:
            raise HTTPException(status_code=404, detail="assignment not found") from e
    return recheck


def _serialize(a: Assignment) -> dict:
    return {
        "id": a.id, "tenant": a.tenant, "pack_id": a.pack_id, "agent_id": a.agent_id,
        "rfp_title": a.rfp_title, "section_id": a.section_id, "section_title": a.section_title,
        "assignee_user_id": a.assignee_user_id, "assigned_by_user_id": a.assigned_by_user_id,
        "question": a.question, "status": a.status, "due_at": a.due_at, "completed_at": a.completed_at,
    }


class SectionAssignIn(BaseModel):
    section_id: str = Field(min_length=1)
    assignee_user_id: str = Field(min_length=1)
    questions: list[str] = Field(default_factory=list)
    title: str | None = None
    due_at: datetime | None = None


class QuestionAssignIn(BaseModel):
    assignee_user_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    due_at: datetime | None = None


class BulkAssignBody(BaseModel):
    pack_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    rfp_title: str | None = None
    sections: list[SectionAssignIn] = Field(default_factory=list)
    questions: list[QuestionAssignIn] = Field(default_factory=list)


@router.post("/bulk")
async def bulk_assign(body: BulkAssignBody, request: Request,
                      tenant: str = Depends(authed_tenant),
                      claims: dict = Depends(current_claims), _role: dict = _admin,
                      svc=Depends(get_assignments), packs=Depends(get_rfp_packs),
                      tree=Depends(get_pack_tree), users=Depends(get_user_store)) -> list[dict]:
    pack, recheck = await _resolve_pack(request, tenant, body.pack_id, packs)
    if body.agent_id != pack.agent_id:
        raise HTTPException(status_code=422, detail="agent does not match RFP pack")

    assignee_ids = {row.assignee_user_id for row in (*body.sections, *body.questions)}
    for assignee_id in assignee_ids:
        assignee = await users.get_by_id(assignee_id)
        if assignee is None or assignee.tenant != tenant:
            raise HTTPException(status_code=404, detail="assignee not found")

    trusted_sections: list[SectionAssignBody] = []
    trusted_agent_id = pack.agent_id
    trusted_rfp_title = pack.title
    if body.sections:
        persisted_sections = await tree.list_tree(tenant, body.pack_id)
        sections_by_id = {section["id"]: section for section in persisted_sections}
        parent_ids = {section["parent_id"] for section in persisted_sections if section["parent_id"]}
        for row in body.sections:
            try:
                await tree.get_section_for_pack(tenant, body.pack_id, row.section_id)
            except PackSectionNotFound as e:
                raise HTTPException(status_code=404, detail="section not found in RFP pack") from e
            section = sections_by_id.get(row.section_id)
            if section is None:
                raise HTTPException(status_code=404, detail="section not found in RFP pack")
            if row.section_id in parent_ids:
                raise HTTPException(status_code=422, detail="section must be a leaf")
            questions = [question["text"] for question in section["questions"]]
            if not questions:
                raise HTTPException(status_code=422, detail="leaf section has no questions")
            trusted_sections.append(SectionAssignBody(
                section_id=row.section_id,
                assignee_user_id=row.assignee_user_id,
                questions=questions,
                title=section["name"],
                due_at=row.due_at,
            ))

    try:
        saved = await svc.bulk_assign(
            tenant, claims["sub"], pack_id=body.pack_id, agent_id=trusted_agent_id,
            rfp_title=trusted_rfp_title, sections=trusted_sections,
            questions=[QuestionAssignBody(assignee_user_id=q.assignee_user_id, question=q.question,
                                          due_at=q.due_at) for q in body.questions],
            recheck_worker=recheck)
    except AssignmentError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return [_serialize(a) for a in saved]


@router.get("")
async def list_assignments(pack_id: str | None = None, assignee_user_id: str | None = None,
                           status: str | None = None, tenant: str = Depends(authed_tenant),
                           svc=Depends(get_assignments)) -> list[dict]:
    items = await svc.list(tenant, pack_id=pack_id, assignee_user_id=assignee_user_id, status=status)
    return [_serialize(a) for a in items]


@router.get("/dashboard")
async def dashboard(pack_id: str, member_user_ids: str, tenant: str = Depends(authed_tenant),
                    svc=Depends(get_assignments)) -> list[dict]:
    """member_user_ids: comma-separated list of tenant member user ids to roll up."""
    ids = [u for u in member_user_ids.split(",") if u]
    return await svc.dashboard(tenant, pack_id, ids)


class UpdateStatusBody(BaseModel):
    status: str


@router.put("/{assignment_id}/status")
async def update_status(assignment_id: str, body: UpdateStatusBody, request: Request,
                        tenant: str = Depends(authed_tenant),
                        claims: dict = Depends(current_claims), svc=Depends(get_assignments),
                        packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree)) -> dict:
    """An assignee may only update the status of their own assignment; owner/admin can too."""
    match = await _get_assignment(svc, tenant, assignment_id)
    recheck = await _resolve_assignment_pack(request, tenant, match, packs, tree)
    is_owner_or_admin = claims.get("role") in (Role.owner.value, Role.admin.value)
    if not is_owner_or_admin and match.assignee_user_id != claims["sub"]:
        raise HTTPException(status_code=403, detail="you cannot update this assignment")
    try:
        await recheck()
        updated = await svc.update_status(tenant, assignment_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _serialize(updated)


class ReassignBody(BaseModel):
    assignee_user_id: str | None = None
    question: str | None = None
    due_at: datetime | None = None


@router.put("/{assignment_id}")
async def reassign(assignment_id: str, body: ReassignBody, request: Request,
                   tenant: str = Depends(authed_tenant),
                   _role: dict = _admin, svc=Depends(get_assignments),
                   packs=Depends(get_rfp_packs), tree=Depends(get_pack_tree),
                   users=Depends(get_user_store)) -> dict:
    existing = await _get_assignment(svc, tenant, assignment_id)
    recheck = await _resolve_assignment_pack(request, tenant, existing, packs, tree)
    if body.assignee_user_id is not None:
        assignee = await users.get_by_id(body.assignee_user_id)
        if assignee is None or assignee.tenant != tenant:
            raise HTTPException(status_code=404, detail="assignee not found")
    if body.question is not None and existing.section_id is not None:
        raise HTTPException(status_code=422, detail="section assignment questions are read-only")

    try:
        await recheck()
        updated = await svc.reassign(tenant, assignment_id, assignee_user_id=body.assignee_user_id,
                                     question=body.question, due_at=body.due_at)
    except AssignmentNotFound as e:
        raise HTTPException(status_code=404, detail="assignment not found") from e
    return _serialize(updated)


@router.delete("/section/{pack_id}/{section_id}")
async def delete_by_section(pack_id: str, section_id: str, request: Request,
                            tenant: str = Depends(authed_tenant), _role: dict = _admin,
                            svc=Depends(get_assignments), packs=Depends(get_rfp_packs),
                            tree=Depends(get_pack_tree)) -> dict:
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    try:
        await tree.get_section_for_pack(tenant, pack_id, section_id)
    except PackSectionNotFound as e:
        raise HTTPException(status_code=404, detail="no assignments found for this section") from e
    await recheck()
    deleted = await svc.delete_by_section(tenant, pack_id, section_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="no assignments found for this section")
    return {"section_id": section_id, "deleted_count": deleted}


@router.delete("/pack/{pack_id}")
async def delete_by_pack(pack_id: str, request: Request,
                         tenant: str = Depends(authed_tenant), _role: dict = _admin,
                         svc=Depends(get_assignments), packs=Depends(get_rfp_packs)) -> dict:
    _pack, recheck = await _resolve_pack(request, tenant, pack_id, packs)
    await recheck()
    deleted = await svc.delete_by_pack(tenant, pack_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="no assignments found for this pack")
    return {"pack_id": pack_id, "deleted_count": deleted}


class ReminderBody(BaseModel):
    pack_id: str
    assignee_user_id: str = Field(min_length=1)


@router.post("/send-reminder")
async def send_reminder(body: ReminderBody, request: Request,
                        tenant: str = Depends(authed_tenant), _role: dict = _admin,
                        svc=Depends(get_assignments), packs=Depends(get_rfp_packs),
                        tree=Depends(get_pack_tree), users=Depends(get_user_store)) -> dict:
    _pack, recheck = await _resolve_pack(request, tenant, body.pack_id, packs)
    pending = await svc.list(tenant, pack_id=body.pack_id, assignee_user_id=body.assignee_user_id,
                             status="pending")
    for assignment in pending:
        await _resolve_assignment_pack(request, tenant, assignment, packs, tree)
    if not pending:
        raise HTTPException(status_code=404, detail="no pending assignments found to remind")
    user = await users.get_by_id(body.assignee_user_id)
    if user is None or user.tenant != tenant:
        raise HTTPException(status_code=404, detail="assignee not found")
    if not user.email:
        return {"reminders_sent": 0, "reminders_failed": len(pending), "reason": "no email address on file"}
    lines = "\n".join(f"- {a.section_title or a.question}" for a in pending)
    await recheck()
    get_email_sender().send(to=user.email, subject=f"Reminder: {len(pending)} pending RFP section(s)",
                            body=f"You have {len(pending)} pending item(s) to complete:\n{lines}")
    return {"reminders_sent": len(pending), "reminders_failed": 0}
