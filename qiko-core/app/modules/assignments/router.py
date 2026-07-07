"""Section-assignment HTTP API (tenant-scoped): assign RFP sections/questions to team members,
track status, and roll it up into a per-member dashboard."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, current_claims, get_assignments, require_role
from app.modules.assignments.service import (
    Assignment,
    AssignmentError,
    AssignmentNotFound,
    QuestionAssignBody,
    SectionAssignBody,
)
from app.modules.email.sender import get_email_sender
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/assignments", tags=["assignments"])
_admin = Depends(require_role(Role.admin))


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
    questions: list[str] = Field(min_length=1)
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
async def bulk_assign(body: BulkAssignBody, tenant: str = Depends(authed_tenant),
                      claims: dict = Depends(current_claims), _role: dict = _admin,
                      svc=Depends(get_assignments)) -> list[dict]:
    try:
        saved = await svc.bulk_assign(
            tenant, claims["sub"], pack_id=body.pack_id, agent_id=body.agent_id, rfp_title=body.rfp_title,
            sections=[SectionAssignBody(section_id=s.section_id, assignee_user_id=s.assignee_user_id,
                                        questions=s.questions, title=s.title, due_at=s.due_at)
                     for s in body.sections],
            questions=[QuestionAssignBody(assignee_user_id=q.assignee_user_id, question=q.question,
                                          due_at=q.due_at) for q in body.questions])
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
async def update_status(assignment_id: str, body: UpdateStatusBody, tenant: str = Depends(authed_tenant),
                        claims: dict = Depends(current_claims), svc=Depends(get_assignments)) -> dict:
    """An assignee may only update the status of their own assignment; owner/admin can too."""
    existing = await svc.list(tenant)
    match = next((a for a in existing if a.id == assignment_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    is_owner_or_admin = claims.get("role") in (Role.owner.value, Role.admin.value)
    if not is_owner_or_admin and match.assignee_user_id != claims["sub"]:
        raise HTTPException(status_code=403, detail="you cannot update this assignment")
    try:
        updated = await svc.update_status(tenant, assignment_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _serialize(updated)


class ReassignBody(BaseModel):
    assignee_user_id: str | None = None
    question: str | None = None
    due_at: datetime | None = None


@router.put("/{assignment_id}")
async def reassign(assignment_id: str, body: ReassignBody, tenant: str = Depends(authed_tenant),
                   _role: dict = _admin, svc=Depends(get_assignments)) -> dict:
    try:
        updated = await svc.reassign(tenant, assignment_id, assignee_user_id=body.assignee_user_id,
                                     question=body.question, due_at=body.due_at)
    except AssignmentNotFound as e:
        raise HTTPException(status_code=404, detail="assignment not found") from e
    return _serialize(updated)


@router.delete("/section/{pack_id}/{section_id}")
async def delete_by_section(pack_id: str, section_id: str, tenant: str = Depends(authed_tenant),
                            _role: dict = _admin, svc=Depends(get_assignments)) -> dict:
    deleted = await svc.delete_by_section(tenant, pack_id, section_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="no assignments found for this section")
    return {"section_id": section_id, "deleted_count": deleted}


@router.delete("/pack/{pack_id}")
async def delete_by_pack(pack_id: str, tenant: str = Depends(authed_tenant),
                         _role: dict = _admin, svc=Depends(get_assignments)) -> dict:
    deleted = await svc.delete_by_pack(tenant, pack_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="no assignments found for this pack")
    return {"pack_id": pack_id, "deleted_count": deleted}


class ReminderBody(BaseModel):
    pack_id: str
    assignee_user_id: str | None = None
    assignee_email: str | None = None


@router.post("/send-reminder")
async def send_reminder(body: ReminderBody, tenant: str = Depends(authed_tenant), _role: dict = _admin,
                        svc=Depends(get_assignments)) -> dict:
    pending = await svc.list(tenant, pack_id=body.pack_id, assignee_user_id=body.assignee_user_id,
                             status="pending")
    if not pending:
        raise HTTPException(status_code=404, detail="no pending assignments found to remind")
    if not body.assignee_email:
        return {"reminders_sent": 0, "reminders_failed": len(pending), "reason": "no email address on file"}
    lines = "\n".join(f"- {a.section_title or a.question}" for a in pending)
    get_email_sender().send(to=body.assignee_email, subject=f"Reminder: {len(pending)} pending RFP section(s)",
                            body=f"You have {len(pending)} pending item(s) to complete:\n{lines}")
    return {"reminders_sent": len(pending), "reminders_failed": 0}
