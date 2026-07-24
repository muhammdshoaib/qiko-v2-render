"""Section-assignment / collaboration: assign RFP pack sections (or standalone questions) to
tenant members, track completion, and roll it up into a per-member dashboard.

Port of the real, working feature from qiko-backend (Laravel) branch chat-imp-idg's
QuestionAssignmentController + AssignedQuestion model -- tenant-scoped here (qiko-core's unit of
isolation) rather than the Laravel app's separate Team entity.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

STATUSES = ("pending", "completed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AssignmentError(Exception):
    pass


class AssignmentNotFound(Exception):
    pass


@dataclass
class Assignment:
    id: str
    tenant: str
    pack_id: str
    agent_id: str
    assignee_user_id: str
    assigned_by_user_id: str
    question: str
    section_id: str | None = None
    section_title: str | None = None
    rfp_title: str | None = None
    status: str = "pending"
    due_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)


class AssignmentStore(Protocol):
    async def add(self, a: Assignment) -> Assignment: ...
    async def list(self, tenant: str, *, pack_id: str | None = None,
                   assignee_user_id: str | None = None, status: str | None = None) -> list[Assignment]: ...
    async def get(self, tenant: str, assignment_id: str) -> Assignment | None: ...
    async def update(self, tenant: str, assignment_id: str, **fields) -> Assignment: ...
    async def delete_by_section(self, tenant: str, pack_id: str, section_id: str) -> int: ...
    async def delete_by_pack(self, tenant: str, pack_id: str) -> int: ...


@dataclass
class InMemoryAssignmentStore:
    _by_tenant: dict[str, list[Assignment]] = field(default_factory=dict)

    async def add(self, a: Assignment) -> Assignment:
        self._by_tenant.setdefault(a.tenant, []).append(a)
        return a

    async def list(self, tenant: str, *, pack_id: str | None = None,
                   assignee_user_id: str | None = None, status: str | None = None) -> list[Assignment]:
        items = self._by_tenant.get(tenant, [])
        if pack_id is not None:
            items = [a for a in items if a.pack_id == pack_id]
        if assignee_user_id is not None:
            items = [a for a in items if a.assignee_user_id == assignee_user_id]
        if status is not None:
            items = [a for a in items if a.status == status]
        return list(items)

    async def get(self, tenant: str, assignment_id: str) -> Assignment | None:
        return next((a for a in self._by_tenant.get(tenant, []) if a.id == assignment_id), None)

    async def update(self, tenant: str, assignment_id: str, **fields) -> Assignment:
        a = await self.get(tenant, assignment_id)
        if a is None:
            raise AssignmentNotFound(assignment_id)
        for k, v in fields.items():
            setattr(a, k, v)
        return a

    async def delete_by_section(self, tenant: str, pack_id: str, section_id: str) -> int:
        items = self._by_tenant.get(tenant, [])
        keep = [a for a in items if not (a.pack_id == pack_id and a.section_id == section_id)]
        removed = len(items) - len(keep)
        self._by_tenant[tenant] = keep
        return removed

    async def delete_by_pack(self, tenant: str, pack_id: str) -> int:
        items = self._by_tenant.get(tenant, [])
        keep = [a for a in items if a.pack_id != pack_id]
        removed = len(items) - len(keep)
        self._by_tenant[tenant] = keep
        return removed


@dataclass
class SectionAssignBody:
    section_id: str
    assignee_user_id: str
    questions: list[str]
    title: str | None = None
    due_at: datetime | None = None


@dataclass
class QuestionAssignBody:
    assignee_user_id: str
    question: str
    due_at: datetime | None = None


@dataclass
class AssignmentService:
    store: AssignmentStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryAssignmentStore()

    async def bulk_assign(self, tenant: str, assigned_by: str, *, pack_id: str, agent_id: str,
                          rfp_title: str | None = None, sections: list[SectionAssignBody] | None = None,
                          questions: list[QuestionAssignBody] | None = None) -> list[Assignment]:
        sections = sections or []
        questions = questions or []
        if not sections and not questions:
            raise AssignmentError("provide at least one section or question to assign")

        saved: list[Assignment] = []
        for row in sections:
            for q in row.questions:
                saved.append(await self.store.add(Assignment(
                    id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, agent_id=agent_id,
                    rfp_title=rfp_title, section_id=row.section_id, section_title=row.title,
                    assignee_user_id=row.assignee_user_id, assigned_by_user_id=assigned_by,
                    question=q, due_at=row.due_at)))
        for row in questions:
            saved.append(await self.store.add(Assignment(
                id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, agent_id=agent_id,
                rfp_title=rfp_title, assignee_user_id=row.assignee_user_id,
                assigned_by_user_id=assigned_by, question=row.question, due_at=row.due_at)))
        return saved

    async def list(self, tenant: str, *, pack_id: str | None = None,
                   assignee_user_id: str | None = None, status: str | None = None) -> list[Assignment]:
        return await self.store.list(tenant, pack_id=pack_id, assignee_user_id=assignee_user_id, status=status)

    async def update_status(self, tenant: str, assignment_id: str, status: str) -> Assignment:
        if status not in STATUSES:
            raise ValueError(f"invalid status '{status}', must be one of {STATUSES}")
        completed_at = _now() if status == "completed" else None
        return await self.store.update(tenant, assignment_id, status=status, completed_at=completed_at)

    async def reassign(self, tenant: str, assignment_id: str, *, assignee_user_id: str | None = None,
                       question: str | None = None, due_at: datetime | None = None) -> Assignment:
        fields = {}
        if assignee_user_id is not None:
            fields["assignee_user_id"] = assignee_user_id
        if question is not None:
            fields["question"] = question
        if due_at is not None:
            fields["due_at"] = due_at
        return await self.store.update(tenant, assignment_id, **fields)

    async def delete_by_section(self, tenant: str, pack_id: str, section_id: str) -> int:
        return await self.store.delete_by_section(tenant, pack_id, section_id)

    async def delete_by_pack(self, tenant: str, pack_id: str) -> int:
        return await self.store.delete_by_pack(tenant, pack_id)

    async def dashboard(self, tenant: str, pack_id: str, member_user_ids: list[str]) -> list[dict]:
        """Per-member rollup for a pack: assigned/completed/pending counts, progress %, overdue
        flag, and the list of sections they own."""
        now = _now()
        rows = []
        for uid in member_user_ids:
            items = await self.store.list(tenant, pack_id=pack_id, assignee_user_id=uid)
            assigned = len(items)
            completed = len([a for a in items if a.status == "completed"])
            pending = assigned - completed
            progress = round(completed / assigned * 100) if assigned else 0
            overdue = any(a.status == "pending" and a.due_at and a.due_at < now for a in items)
            status = "overdue" if overdue else ("pending" if pending else "completed")
            sections = {}
            for a in items:
                if a.section_id:
                    sections[a.section_id] = {"section_id": a.section_id, "section_title": a.section_title,
                                              "rfp_title": a.rfp_title, "due_at": a.due_at}
            rows.append({"user_id": uid, "assigned": assigned, "completed": completed, "pending": pending,
                        "progress": progress, "status": status, "sections": list(sections.values())})
        return rows
