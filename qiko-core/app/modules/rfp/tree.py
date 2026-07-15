"""Section -> question tree for an RFP pack (the validated tender-cockpit model).

The flat PackRequirement list (one answer each, see service.py) is what /extract produces and what
the exports iterate; this module adds the reviewer-facing tree on top: a pack owns sections, each
section owns questions, with per-question lock/draft/word-limit and section-level
reviewer/weighting/manual/kb-gap. Source field names mirror the idg-sales FE (IDGRfpSection /
IDGRfpSectionQuestion) so the FE port is 1:1.

Lock roll-up: a (non-manual) section is locked once all its questions are locked; a pack can only
advance to `final` once every section is locked. A locked question's user_draft is the source of
truth in exports (idg-worker's human-answer overlay governance).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

# Section status vocabulary, mirroring the FE cockpit's local `status` union.
SECTION_STATUSES = ("not_generated", "generating", "draft_ready", "reviewing", "locked", "manual", "overdue")


@dataclass
class PackSection:
    id: str
    tenant: str
    pack_id: str
    code: str
    name: str
    page: int | None = None
    weighting: str = ""
    status: str = "not_generated"
    parent_id: str | None = None
    assigned_reviewer_user_id: str | None = None
    assigned_reviewer_name: str = ""
    due_date: str | None = None
    manual: bool = False
    kb_gap: bool = False
    order_index: int = 0


@dataclass
class PackQuestion:
    id: str
    tenant: str
    pack_id: str
    section_id: str
    text: str
    req_id: str = ""  # links back to the flat PackRequirement -> export overlay
    word_limit: int | None = None
    ai_answer: str = ""
    ai_sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    decision: str = ""
    kb_gap: bool = False
    locked: bool = False
    user_draft: str = ""
    order_index: int = 0


class PackSectionNotFound(Exception):
    pass


class PackQuestionNotFound(Exception):
    pass


class SectionStore(Protocol):
    async def add(self, section: PackSection) -> PackSection: ...
    async def list(self, tenant: str, pack_id: str) -> list[PackSection]: ...
    async def get(self, tenant: str, section_id: str) -> PackSection | None: ...
    async def update(self, tenant: str, section_id: str, **fields) -> PackSection: ...
    async def delete(self, tenant: str, section_id: str) -> None: ...
    async def delete_for_pack(self, tenant: str, pack_id: str) -> None: ...


class QuestionStore(Protocol):
    async def add(self, question: PackQuestion) -> PackQuestion: ...
    async def list(self, tenant: str, pack_id: str) -> list[PackQuestion]: ...
    async def list_for_section(self, tenant: str, section_id: str) -> list[PackQuestion]: ...
    async def get(self, tenant: str, question_id: str) -> PackQuestion | None: ...
    async def update(self, tenant: str, question_id: str, **fields) -> PackQuestion: ...
    async def delete(self, tenant: str, question_id: str) -> None: ...
    async def delete_for_section(self, tenant: str, section_id: str) -> None: ...
    async def delete_for_pack(self, tenant: str, pack_id: str) -> None: ...


@dataclass
class InMemorySectionStore:
    _rows: list[PackSection] = field(default_factory=list)

    async def add(self, section: PackSection) -> PackSection:
        self._rows.append(section)
        return section

    async def list(self, tenant: str, pack_id: str) -> list[PackSection]:
        return sorted([s for s in self._rows if s.tenant == tenant and s.pack_id == pack_id],
                      key=lambda s: s.order_index)

    async def get(self, tenant: str, section_id: str) -> PackSection | None:
        return next((s for s in self._rows if s.id == section_id and s.tenant == tenant), None)

    async def update(self, tenant: str, section_id: str, **fields) -> PackSection:
        section = await self.get(tenant, section_id)
        if section is None:
            raise PackSectionNotFound(section_id)
        for k, v in fields.items():
            setattr(section, k, v)
        return section

    async def delete(self, tenant: str, section_id: str) -> None:
        self._rows = [s for s in self._rows if not (s.id == section_id and s.tenant == tenant)]

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        self._rows = [s for s in self._rows if not (s.pack_id == pack_id and s.tenant == tenant)]


@dataclass
class InMemoryQuestionStore:
    _rows: list[PackQuestion] = field(default_factory=list)

    async def add(self, question: PackQuestion) -> PackQuestion:
        self._rows.append(question)
        return question

    async def list(self, tenant: str, pack_id: str) -> list[PackQuestion]:
        return sorted([q for q in self._rows if q.tenant == tenant and q.pack_id == pack_id],
                      key=lambda q: q.order_index)

    async def list_for_section(self, tenant: str, section_id: str) -> list[PackQuestion]:
        return sorted([q for q in self._rows if q.tenant == tenant and q.section_id == section_id],
                      key=lambda q: q.order_index)

    async def get(self, tenant: str, question_id: str) -> PackQuestion | None:
        return next((q for q in self._rows if q.id == question_id and q.tenant == tenant), None)

    async def update(self, tenant: str, question_id: str, **fields) -> PackQuestion:
        question = await self.get(tenant, question_id)
        if question is None:
            raise PackQuestionNotFound(question_id)
        for k, v in fields.items():
            setattr(question, k, v)
        return question

    async def delete(self, tenant: str, question_id: str) -> None:
        self._rows = [q for q in self._rows if not (q.id == question_id and q.tenant == tenant)]

    async def delete_for_section(self, tenant: str, section_id: str) -> None:
        self._rows = [q for q in self._rows if not (q.section_id == section_id and q.tenant == tenant)]

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        self._rows = [q for q in self._rows if not (q.pack_id == pack_id and q.tenant == tenant)]


def _top_level_code(code: str) -> str:
    """The section a dotted extraction id belongs to: "B1.1"/"B1.2" -> "B1", "A1" -> "A1"."""
    return (code or "").split(".")[0] or code


@dataclass
class PackTreeService:
    """Owns the section+question tree for RFP packs, with the lock roll-up and overview metrics."""
    sections: SectionStore = None  # type: ignore[assignment]
    questions: QuestionStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.sections is None:
            self.sections = InMemorySectionStore()
        if self.questions is None:
            self.questions = InMemoryQuestionStore()

    # --- sections ---
    async def add_section(self, tenant: str, pack_id: str, *, code: str, name: str,
                          page: int | None = None, weighting: str = "", parent_id: str | None = None,
                          assigned_reviewer_user_id: str | None = None, assigned_reviewer_name: str = "",
                          due_date: str | None = None, manual: bool = False) -> PackSection:
        existing = await self.sections.list(tenant, pack_id)
        section = PackSection(
            id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, code=code, name=name, page=page,
            weighting=weighting, status="manual" if manual else "not_generated", parent_id=parent_id,
            assigned_reviewer_user_id=assigned_reviewer_user_id, assigned_reviewer_name=assigned_reviewer_name,
            due_date=due_date, manual=manual, order_index=len(existing))
        return await self.sections.add(section)

    async def get_section(self, tenant: str, section_id: str) -> PackSection:
        section = await self.sections.get(tenant, section_id)
        if section is None:
            raise PackSectionNotFound(section_id)
        return section

    async def update_section(self, tenant: str, section_id: str, **fields) -> PackSection:
        await self.get_section(tenant, section_id)
        clean = {k: v for k, v in fields.items() if v is not None}
        section = await self.sections.update(tenant, section_id, **clean) if clean \
            else await self.get_section(tenant, section_id)
        return await self._recompute_section(tenant, section_id) if "manual" in clean else section

    async def delete_section(self, tenant: str, section_id: str) -> None:
        await self.get_section(tenant, section_id)
        await self.questions.delete_for_section(tenant, section_id)
        await self.sections.delete(tenant, section_id)

    # --- questions ---
    async def add_question(self, tenant: str, section_id: str, *, text: str, req_id: str = "",
                           word_limit: int | None = None) -> PackQuestion:
        section = await self.get_section(tenant, section_id)
        siblings = await self.questions.list_for_section(tenant, section_id)
        question = PackQuestion(id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=section.pack_id,
                                section_id=section_id, text=text, req_id=req_id, word_limit=word_limit,
                                order_index=len(siblings))
        added = await self.questions.add(question)
        await self._recompute_section(tenant, section_id)
        return added

    async def get_question(self, tenant: str, question_id: str) -> PackQuestion:
        question = await self.questions.get(tenant, question_id)
        if question is None:
            raise PackQuestionNotFound(question_id)
        return question

    async def update_question(self, tenant: str, question_id: str, **fields) -> PackQuestion:
        question = await self.get_question(tenant, question_id)
        clean = {k: v for k, v in fields.items() if v is not None}
        if clean:
            question = await self.questions.update(tenant, question_id, **clean)
        await self._recompute_section(tenant, question.section_id)
        return question

    async def delete_question(self, tenant: str, question_id: str) -> None:
        question = await self.get_question(tenant, question_id)
        await self.questions.delete(tenant, question_id)
        await self._recompute_section(tenant, question.section_id)

    async def save_user_draft(self, tenant: str, question_id: str, user_draft: str) -> PackQuestion:
        question = await self.get_question(tenant, question_id)
        updated = await self.questions.update(tenant, question_id, user_draft=user_draft)
        await self._recompute_section(tenant, question.section_id)
        return updated

    async def apply_generation(self, tenant: str, question_id: str, *, ai_answer: str,
                               ai_sources: list[str], confidence: float, decision: str,
                               kb_gap: bool) -> PackQuestion:
        """Persist an agentcore draft onto a question and roll the result up to its section."""
        question = await self.get_question(tenant, question_id)
        updated = await self.questions.update(tenant, question_id, ai_answer=ai_answer,
                                              ai_sources=ai_sources, confidence=confidence,
                                              decision=decision, kb_gap=kb_gap)
        await self._recompute_section(tenant, question.section_id)
        return updated

    # --- lock roll-up ---
    async def lock_question(self, tenant: str, question_id: str, *, locked: bool = True) -> PackQuestion:
        question = await self.get_question(tenant, question_id)
        updated = await self.questions.update(tenant, question_id, locked=locked)
        await self._recompute_section(tenant, question.section_id)
        return updated

    async def lock_all_in_section(self, tenant: str, section_id: str) -> PackSection:
        await self.get_section(tenant, section_id)
        for q in await self.questions.list_for_section(tenant, section_id):
            if not q.locked:
                await self.questions.update(tenant, q.id, locked=True)
        return await self._recompute_section(tenant, section_id)

    async def _recompute_section(self, tenant: str, section_id: str) -> PackSection:
        """Roll question state up to the section: a section is locked once all its questions are
        locked; kb_gap surfaces if any question found no KB content."""
        section = await self.sections.get(tenant, section_id)
        if section is None:
            raise PackSectionNotFound(section_id)
        qs = await self.questions.list_for_section(tenant, section_id)
        kb_gap = any(q.kb_gap for q in qs)
        if qs and all(q.locked for q in qs):
            status = "locked"
        elif section.manual:
            status = "manual"
        elif any(q.ai_answer or q.user_draft for q in qs):
            status = "draft_ready"
        else:
            status = "not_generated"
        return await self.sections.update(tenant, section_id, status=status, kb_gap=kb_gap)

    async def all_sections_locked(self, tenant: str, pack_id: str) -> bool:
        sections = await self.sections.list(tenant, pack_id)
        return bool(sections) and all(s.status == "locked" for s in sections)

    # --- reads ---
    async def list_tree(self, tenant: str, pack_id: str) -> list[dict]:
        sections = await self.sections.list(tenant, pack_id)
        questions = await self.questions.list(tenant, pack_id)
        by_section: dict[str, list[PackQuestion]] = {}
        for q in questions:
            by_section.setdefault(q.section_id, []).append(q)
        out: list[dict] = []
        for s in sections:
            sq = by_section.get(s.id, [])
            out.append({**s.__dict__, "questions": [q.__dict__ for q in sq],
                        "avg_confidence": round(sum(q.confidence for q in sq) / len(sq), 2) if sq else 0.0})
        return out

    async def overview(self, tenant: str, pack_id: str) -> dict:
        sections = await self.sections.list(tenant, pack_id)
        questions = await self.questions.list(tenant, pack_id)
        drafted = [q for q in questions if q.ai_answer or q.user_draft]
        for_human_review = [q for q in questions if q.decision == "human_review" and not q.locked]
        kb_sources = {c for q in questions for c in q.ai_sources}
        return {
            "sections": len(sections),
            "sections_locked": sum(1 for s in sections if s.status == "locked"),
            "questions": len(questions),
            "ai_drafted": len(drafted),
            "ai_drafted_total": len(questions),
            "for_human_review": len(for_human_review),
            "kb_sources": len(kb_sources),
            "kb_gaps": sum(1 for q in questions if q.kb_gap),
            "can_finalize": await self.all_sections_locked(tenant, pack_id),
        }

    # --- extraction wiring ---
    async def populate_from_extraction(self, tenant: str, pack_id: str, extracted: list[dict]) -> list[PackSection]:
        """Group extracted requirement items into the section->question tree: items sharing a
        top-level code ("B1.1"/"B1.2" -> "B1") become one section, each item a question. A section
        whose items are all MANUAL/COMPLIANCE is flagged manual (team-completed, not AI-drafted)."""
        await self.sections.delete_for_pack(tenant, pack_id)
        await self.questions.delete_for_pack(tenant, pack_id)
        groups: dict[str, list[dict]] = {}
        for item in extracted:
            groups.setdefault(_top_level_code(item["id"]), []).append(item)
        created: list[PackSection] = []
        for order, (code, items) in enumerate(groups.items()):
            heading = items[0]["title"].split(" \u2014 ")[0].strip() or items[0]["title"]
            manual = all(i["classification"] in {"MANUAL", "COMPLIANCE"} for i in items)
            section = PackSection(id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, code=code,
                                  name=heading, status="manual" if manual else "not_generated",
                                  manual=manual, order_index=order)
            await self.sections.add(section)
            for qi, item in enumerate(items):
                await self.questions.add(PackQuestion(
                    id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, section_id=section.id,
                    text=item["requirement"], req_id=item["id"], order_index=qi))
            created.append(section)
        return created

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        await self.questions.delete_for_pack(tenant, pack_id)
        await self.sections.delete_for_pack(tenant, pack_id)
