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

import re
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.modules.rfp.extraction import split_subsections

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
    # Stepper (Upload->Parsed->Assigned->Drafting->Review) per-section reviewer: a tenant user id
    # plus a denormalised display name for easy render. Metadata only -- it does NOT gate whether
    # or what answers are generated (drafts run for every section regardless of assignment).
    reviewer: str | None = None
    reviewer_name: str = ""
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
    confidence: float = 0.0  # the writer's self-reported confidence (0..1)
    grounding: float = 0.0   # the independent critic's grounding score (0..1), distinct from above
    gaps: str = ""           # the writer's note of what the evidence did not let it support
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


# A "section token": a leading letter-run + number ("B1"), a bare letter-run ("A"), or a bare
# number ("2"). Everything after it (a dotted sub-part ".1", or a legacy "_unpriced" suffix from an
# old flat backfill) is stripped so finer ids coalesce under the top-level section they belong to.
_SECTION_TOKEN = re.compile(r"^([A-Za-z]+\d+|[A-Za-z]+|\d+)")


def _top_level_code(code: str) -> str:
    """The top-level section a (possibly dotted or legacy-flat) extraction id belongs to.

    "B1.1"/"B1.2" -> "B1"; "A1" -> "A1"; "A1_unpriced"/"A1_priced" -> "A1"; "2" -> "2". Coalescing
    finer/legacy ids under their leading section token keeps an old flat backfill (dozens of ids
    like "A1_unpriced") from exploding into dozens of top-level sections."""
    head = (code or "").split(".")[0]
    match = _SECTION_TOKEN.match(head)
    return match.group(1) if match else (head or code)


def _is_subpart(code: str) -> bool:
    """A dotted extraction id ("B1.1") denotes a distinct, independently gradeable sub-section; a
    plain id ("B1", "A1", "A1_unpriced") is answered directly on its top-level section."""
    return "." in (code or "")


def _section_heading(items: list[dict]) -> str:
    """The top-level section's display name: a plain item's own title if one exists, otherwise the
    parent heading carried on a sub-part's title (the text before the em-dash separator the
    extractor emits, e.g. "Organisational Structure ... - Contractor's Organogram")."""
    for item in items:
        if not _is_subpart(item["id"]):
            return item["title"].strip() or item["title"]
    first = items[0]["title"]
    return first.split(" \u2014 ")[0].strip() or first


def _subsection_name(item: dict) -> str:
    """A sub-section's own name: the sub-part title after the parent-heading prefix, e.g.
    "Contractor's Organogram" from "Organisational Structure ... - Contractor's Organogram"."""
    parts = item["title"].split(" \u2014 ", 1)
    return (parts[1].strip() if len(parts) == 2 else item["title"].strip()) or item["title"]


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

    async def set_reviewer(self, tenant: str, section_id: str, *, reviewer: str | None,
                           reviewer_name: str = "") -> PackSection:
        """Set (or clear, when reviewer is None) the per-section stepper reviewer. Goes straight to
        the store rather than update_section so an explicit None actually clears it (update_section
        drops None fields as "unchanged")."""
        await self.get_section(tenant, section_id)  # 404s (incl. cross-tenant) before mutating
        return await self.sections.update(tenant, section_id, reviewer=reviewer,
                                          reviewer_name=reviewer_name or "")

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
                               kb_gap: bool, grounding: float = 0.0, gaps: str = "") -> PackQuestion:
        """Persist an agentcore draft onto a question and roll the result up to its section.

        `confidence` (the writer's self-report) and `grounding` (the independent critic) are stored
        as DISTINCT values; `gaps` is the writer's note of what the evidence did not support."""
        question = await self.get_question(tenant, question_id)
        updated = await self.questions.update(tenant, question_id, ai_answer=ai_answer,
                                              ai_sources=ai_sources, confidence=confidence,
                                              grounding=grounding, gaps=gaps,
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
        """Roll state up to the section AND, for a sub-sectioned section, up from its child
        sub-sections (mirroring idg: a top-level section with sub-sections is only "locked" once
        every sub-section is locked, and surfaces a KB gap if ANY sub-section has one). A leaf
        section rolls up from its own questions; a parent from its children. Changing a child
        cascades to its parent."""
        section = await self.sections.get(tenant, section_id)
        if section is None:
            raise PackSectionNotFound(section_id)
        all_sections = await self.sections.list(tenant, section.pack_id)
        children = [s for s in all_sections if s.parent_id == section_id]
        qs = await self.questions.list_for_section(tenant, section_id)
        kb_gap = any(q.kb_gap for q in qs) or any(c.kb_gap for c in children)
        has_units = bool(qs or children)
        # Manual (human-owned) children satisfy the lock gate without being AI-lockable, so a
        # (non-manual) parent that mixes manual + AI children can still reach "locked" once its
        # AI children are locked -- otherwise a manual sub-section would block finalize forever.
        all_locked = ((all(q.locked for q in qs) if qs else True)
                      and (all(c.status in ("locked", "manual") for c in children) if children else True))
        drafty = {"draft_ready", "reviewing", "locked"}
        if section.manual:
            # A manual section stays "manual" (human-owned); it is never AI-locked, and a fully
            # manual parent must not flip to "locked" just because its manual children satisfy the
            # gate above.
            status = "manual"
        elif has_units and all_locked:
            status = "locked"
        elif any(q.ai_answer or q.user_draft for q in qs) or any(c.status in drafty for c in children):
            status = "draft_ready"
        else:
            status = "not_generated"
        updated = await self.sections.update(tenant, section_id, status=status, kb_gap=kb_gap)
        if section.parent_id:
            await self._recompute_section(tenant, section.parent_id)
        return updated

    async def all_sections_locked(self, tenant: str, pack_id: str) -> bool:
        """The finalize gate: every TOP-LEVEL section is either locked (AI drafts reviewed +
        locked, rolled up from its children) or manual (human-owned, not AI-lockable). Manual
        sections count as satisfied -- otherwise any pack containing a manual/compliance section
        could never finalize. Child sub-sections are not checked directly here: their state rolls
        up into the parent's status via _recompute_section."""
        sections = await self.sections.list(tenant, pack_id)
        top_level = [s for s in sections if not s.parent_id]
        return bool(top_level) and all(s.status in ("locked", "manual") for s in top_level)

    # --- reads ---
    async def list_tree(self, tenant: str, pack_id: str) -> list[dict]:
        """The flat list of sections (top-level AND their child sub-sections, linked by parent_id --
        the FE nests them via `childrenOf`), each with its own questions plus rolled-up grounding
        metrics so the cockpit can show idg-identical grounding/confidence/gaps per section.

        Rollup (additive fields): `kb_gap` (any descendant leaf is a KB gap), `confidence`/
        `grounding` (avg across drafted descendant leaves, null if none drafted), and
        `subsection_count` (number of direct child sub-sections)."""
        sections = await self.sections.list(tenant, pack_id)
        questions = await self.questions.list(tenant, pack_id)
        by_section: dict[str, list[PackQuestion]] = {}
        for q in questions:
            by_section.setdefault(q.section_id, []).append(q)
        children_of: dict[str, list[PackSection]] = {}
        for s in sections:
            if s.parent_id:
                children_of.setdefault(s.parent_id, []).append(s)

        def leaf_questions(section_id: str) -> list[PackQuestion]:
            """This section's own questions plus every descendant sub-section's -- the leaves the
            metrics roll up from."""
            acc = list(by_section.get(section_id, []))
            for child in children_of.get(section_id, []):
                acc.extend(leaf_questions(child.id))
            return acc

        out: list[dict] = []
        for s in sections:
            own = by_section.get(s.id, [])
            rolled = leaf_questions(s.id)
            drafted = [q for q in rolled if q.ai_answer or q.user_draft]
            # confidence (writer's self-report) and grounding (independent critic) roll up as
            # DISTINCT averages across drafted leaves (null when nothing is drafted yet).
            confidence = round(sum(q.confidence for q in drafted) / len(drafted), 2) if drafted else None
            grounding = round(sum(q.grounding for q in drafted) / len(drafted), 2) if drafted else None
            out.append({
                **s.__dict__,
                "questions": [q.__dict__ for q in own],
                "avg_confidence": round(sum(q.confidence for q in own) / len(own), 2) if own else 0.0,
                # additive rollup for the FE's grounding/confidence/gaps columns
                "kb_gap": any(q.kb_gap for q in rolled),
                "confidence": confidence,
                "grounding": grounding,
                "subsection_count": len(children_of.get(s.id, [])),
            })
        return out

    async def overview(self, tenant: str, pack_id: str) -> dict:
        sections = await self.sections.list(tenant, pack_id)
        questions = await self.questions.list(tenant, pack_id)
        parent_ids = {s.parent_id for s in sections if s.parent_id}
        top_level = [s for s in sections if not s.parent_id]
        # leaves = sub-sections + childless top-level sections (a KB gap is flagged per leaf)
        leaves = [s for s in sections if s.id not in parent_ids]
        drafted = [q for q in questions if q.ai_answer or q.user_draft]
        for_human_review = [q for q in questions if q.decision == "human_review" and not q.locked]
        kb_sources = {c for q in questions for c in q.ai_sources}
        # avg_confidence (writer self-report) and avg_grounding (independent critic) are DISTINCT.
        avg_conf = round(sum(q.confidence for q in drafted) / len(drafted), 2) if drafted else 0.0
        avg_grounding = round(sum(q.grounding for q in drafted) / len(drafted), 2) if drafted else 0.0
        # "AI-drafted" is counted per TOP-LEVEL SECTION (like idg's "8/15"), NOT per leaf question:
        # a top-level section counts as drafted when it (if childless) or any of its sub-sections has
        # an AI/user draft. Counting leaves gave a misleading "3/144".
        drafted_section_ids = {q.section_id for q in drafted}
        children_by_parent: dict[str, list] = {}
        for s in sections:
            if s.parent_id:
                children_by_parent.setdefault(s.parent_id, []).append(s)

        def _section_drafted(sec) -> bool:
            # A top-level section counts as drafted when it has its OWN drafted question OR any of
            # its sub-sections does. A legacy flat-path parent (_build_tree_from_flat) can carry
            # both its own questions AND children, so we must check the parent itself, not only its
            # kids -- otherwise such a parent is undercounted in the overview.
            kids = children_by_parent.get(sec.id) or []
            return sec.id in drafted_section_ids or any(k.id in drafted_section_ids for k in kids)

        top_drafted = sum(1 for s in top_level if _section_drafted(s))
        return {
            "sections": len(top_level),
            "subsections": len(sections) - len(top_level),
            "sections_locked": sum(1 for s in top_level if s.status == "locked"),
            "questions": len(questions),
            "ai_drafted": top_drafted,
            "ai_drafted_total": len(top_level),
            "for_human_review": len(for_human_review),
            "kb_sources": len(kb_sources),
            "kb_gaps": sum(1 for s in leaves if s.kb_gap),
            "avg_confidence": avg_conf,
            "avg_grounding": avg_grounding,
            "can_finalize": await self.all_sections_locked(tenant, pack_id),
        }

    # --- extraction wiring ---
    async def populate_from_extraction(self, tenant: str, pack_id: str, extracted: list[dict]) -> list[PackSection]:
        """Build the two-level section tree from STRUCTURED extracted sections: each element is one
        top-level section with an EXPLICIT `subsections` array. Each section -> one top-level
        PackSection; each sub-section -> a child PackSection (parent_id set) with its own question;
        a section with no sub-sections keeps a single question (its own requirement) on the
        top-level section. A section (or sub-section) that is all MANUAL/COMPLIANCE is flagged
        manual (team-completed, not AI-drafted)."""
        await self.sections.delete_for_pack(tenant, pack_id)
        await self.questions.delete_for_pack(tenant, pack_id)
        return await self._build_tree(tenant, pack_id, extracted)

    async def populate_from_requirements(self, tenant: str, pack_id: str, requirements: list) -> list[PackSection]:
        """Backfill the section->question tree for a pack extracted BEFORE this feature existed:
        packs that pre-date populate_from_extraction have flat PackRequirement rows but no tree, so
        the validated Sections view shows nothing. Reuse those already-stored requirements (NO LLM
        re-run) via the LEGACY coalescing path (group by top-level id, derive sub-sections from the
        requirement text) rather than the structured path, since those rows have no explicit
        `subsections`. Idempotent and tenant-scoped: if a tree already exists for this pack it is
        left untouched (never duplicated)."""
        if await self.sections.list(tenant, pack_id):
            return []  # a tree already exists -- don't rebuild or duplicate it
        extracted = [{"id": r.req_id, "title": r.title, "classification": r.classification,
                      "requirement": r.requirement} for r in requirements]
        return await self._build_tree_from_flat(tenant, pack_id, extracted)

    async def _build_tree(self, tenant: str, pack_id: str, extracted: list[dict]) -> list[PackSection]:
        """Build the two-level section tree from STRUCTURED extracted sections, consuming the
        EXPLICIT `subsections` array on each (no regex over prose).

        For each extracted section -> ONE top-level PackSection. If it has sub-sections, each
        becomes a child PackSection (parent_id set) carrying its own single question, and the
        parent holds NO direct question (it rolls up from its children, mirroring idg's
        answer_subsections aggregation). If it has no sub-sections, the section keeps a single
        question (its own requirement) directly on the top-level section. A section (or
        sub-section) that is entirely MANUAL/COMPLIANCE is flagged manual. Returns every created
        section (top-level and sub-section)."""
        created: list[PackSection] = []
        for order, section in enumerate(extracted):
            subs = section.get("subsections") or []
            if subs:
                manual = all(s["classification"] in {"MANUAL", "COMPLIANCE"} for s in subs)
            else:
                manual = section["classification"] in {"MANUAL", "COMPLIANCE"}
            parent = PackSection(id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id,
                                 code=section["id"], name=section["title"].strip() or section["title"],
                                 status="manual" if manual else "not_generated",
                                 manual=manual, order_index=order)
            await self.sections.add(parent)
            created.append(parent)
            if subs:
                for sub_order, sub in enumerate(subs):
                    sub_manual = sub["classification"] in {"MANUAL", "COMPLIANCE"}
                    child = PackSection(id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id,
                                        code=sub["id"], name=sub["title"].strip() or sub["title"],
                                        parent_id=parent.id,
                                        status="manual" if sub_manual else "not_generated",
                                        manual=sub_manual, order_index=sub_order)
                    await self.sections.add(child)
                    await self.questions.add(PackQuestion(
                        id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, section_id=child.id,
                        text=sub["requirement"], req_id=sub["id"], order_index=0))
                    created.append(child)
            else:
                await self.questions.add(PackQuestion(
                    id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, section_id=parent.id,
                    text=section["requirement"], req_id=section["id"], order_index=0))
        return created

    async def _build_tree_from_flat(self, tenant: str, pack_id: str, extracted: list[dict]) -> list[PackSection]:
        """LEGACY builder for flat backfills (populate_from_requirements): items are grouped by
        top-level section token so an OLD flat backfill whose stored req_ids are dotted ("B1.1",
        "B1.2") or suffixed ("A1_unpriced") coalesces under one top-level section (dotted items ->
        child sub-sections, plain items -> questions) instead of exploding into dozens of top-level
        sections. A single plain item's requirement TEXT is further split via split_subsections
        (dotted "B1.1/B1.2" headings, else "(a)/(b)" clauses) so a coarse legacy section can still
        expand into per-sub-part answers. Returns every created section (top-level and
        sub-section)."""
        groups: dict[str, list[dict]] = {}
        for item in extracted:
            groups.setdefault(_top_level_code(item["id"]), []).append(item)
        created: list[PackSection] = []
        for order, (code, items) in enumerate(groups.items()):
            subs = [i for i in items if _is_subpart(i["id"])]
            plain = [i for i in items if not _is_subpart(i["id"])]
            manual = all(i["classification"] in {"MANUAL", "COMPLIANCE"} for i in items)
            parent = PackSection(id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, code=code,
                                 name=_section_heading(items),
                                 status="manual" if manual else "not_generated",
                                 manual=manual, order_index=order)
            await self.sections.add(parent)
            created.append(parent)

            # Coarse extraction: a single plain item for this section. Derive its sub-sections from
            # the requirement TEXT (idg split_subsections) -- so "B1.1 ...\nB1.2 ..." in the text
            # becomes two independently gradeable child answers without the extractor emitting them.
            if len(plain) == 1 and not subs:
                item = plain[0]
                parts = split_subsections(item["id"], item["requirement"])
                if len(parts) >= 2:
                    created += await self._add_split_children(tenant, pack_id, parent, parts, manual)
                    continue
                # single part -> one question directly on the section (fall through below)

            # plain items answer directly on the top-level section (also the legacy flat-coalesce
            # case where multiple non-dotted ids share one top-level token)
            for qi, item in enumerate(plain):
                await self.questions.add(PackQuestion(
                    id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, section_id=parent.id,
                    text=item["requirement"], req_id=item["id"], order_index=qi))
            # legacy dotted items -> child sub-sections, each its own single question
            for sub_order, item in enumerate(subs):
                sub_manual = item["classification"] in {"MANUAL", "COMPLIANCE"}
                child = PackSection(id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id,
                                    code=item["id"], name=_subsection_name(item), parent_id=parent.id,
                                    status="manual" if sub_manual else "not_generated",
                                    manual=sub_manual, order_index=sub_order)
                await self.sections.add(child)
                await self.questions.add(PackQuestion(
                    id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, section_id=child.id,
                    text=item["requirement"], req_id=item["id"], order_index=0))
                created.append(child)
        return created

    async def _add_split_children(self, tenant: str, pack_id: str, parent: PackSection,
                                   parts: list[dict], manual: bool) -> list[PackSection]:
        """Create one child sub-section (with its own question) per sub-part derived from a coarse
        section's requirement text. The parent then holds no direct questions -- it rolls up from
        its children, mirroring idg's answer_subsections aggregation."""
        created: list[PackSection] = []
        for sub_order, part in enumerate(parts):
            child = PackSection(id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id,
                                code=part["sub_id"], name=part["title"], parent_id=parent.id,
                                status="manual" if manual else "not_generated",
                                manual=manual, order_index=sub_order)
            await self.sections.add(child)
            await self.questions.add(PackQuestion(
                id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id, section_id=child.id,
                text=part["body"], req_id=part["sub_id"], order_index=0))
            created.append(child)
        return created

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        await self.questions.delete_for_pack(tenant, pack_id)
        await self.sections.delete_for_pack(tenant, pack_id)
