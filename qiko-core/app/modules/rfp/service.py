"""RFP pack lifecycle: each pack is one tender a worker is answering, scoped to a tenant + agent.

A pack goes through the same 5-stage pipeline shown in the IDG cockpit prototype:
parsed -> assigned -> drafting -> review -> final. Coverage % (used by Studio's "Avg Readiness"
metric) is answered-requirements / total-requirements for the pack.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

STAGES = ("parsed", "assigned", "drafting", "review", "final")
# An outcome is recorded once a submitted tender's result is known -- separate from `stage`
# (which tracks the drafting pipeline, not the client's decision). "pending" is the implicit
# default (no outcome recorded yet), so it's not stored as a real DB value, just how a None
# outcome_status reads in the API/UI.
OUTCOMES = ("won", "lost", "withdrawn")
LOSS_REASONS = ("price", "technical", "relationship", "timeline", "no_bid_decision", "other")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RfpPack:
    id: str
    tenant: str
    agent_id: str
    title: str
    client_name: str = ""
    deadline: str | None = None
    stage: str = "parsed"
    created_at: datetime = field(default_factory=_now)
    document_text: str = ""
    # Win/Loss Analysis -- see OUTCOMES/LOSS_REASONS above.
    outcome: str | None = None
    outcome_reason: str = ""
    outcome_value: float | None = None
    outcome_at: datetime | None = None
    # Background tender-generation artifacts persisted by the generate_tender_artifacts job, plus
    # its pollable per-artifact progress (see app.modules.rfp.generation gen_status contract).
    brief: dict | None = None
    compliance: list | None = None
    gen_status: dict | None = None


class RfpPackNotFound(Exception):
    pass


class RfpPackStore(Protocol):
    async def add(self, pack: RfpPack) -> RfpPack: ...
    async def list(self, tenant: str, *, agent_id: str | None = None) -> list[RfpPack]: ...
    async def get(self, tenant: str, pack_id: str) -> RfpPack | None: ...
    async def set_stage(self, tenant: str, pack_id: str, stage: str) -> RfpPack: ...
    async def set_document_text(self, tenant: str, pack_id: str, text: str) -> RfpPack: ...
    async def set_outcome(self, tenant: str, pack_id: str, *, outcome: str | None,
                          reason: str, value: float | None) -> RfpPack: ...
    async def set_brief(self, tenant: str, pack_id: str, brief: dict | None) -> RfpPack: ...
    async def set_compliance(self, tenant: str, pack_id: str, items: list | None) -> RfpPack: ...
    async def set_gen_status(self, tenant: str, pack_id: str, status: dict | None) -> RfpPack: ...
    async def delete(self, tenant: str, pack_id: str) -> None: ...


@dataclass
class InMemoryRfpPackStore:
    _by_tenant: dict[str, list[RfpPack]] = field(default_factory=dict)

    async def add(self, pack: RfpPack) -> RfpPack:
        self._by_tenant.setdefault(pack.tenant, []).append(pack)
        return pack

    async def list(self, tenant: str, *, agent_id: str | None = None) -> list[RfpPack]:
        packs = self._by_tenant.get(tenant, [])
        if agent_id is not None:
            packs = [p for p in packs if p.agent_id == agent_id]
        return list(packs)

    async def get(self, tenant: str, pack_id: str) -> RfpPack | None:
        return next((p for p in self._by_tenant.get(tenant, []) if p.id == pack_id), None)

    async def set_stage(self, tenant: str, pack_id: str, stage: str) -> RfpPack:
        pack = await self.get(tenant, pack_id)
        if pack is None:
            raise RfpPackNotFound(pack_id)
        pack.stage = stage
        return pack

    async def set_document_text(self, tenant: str, pack_id: str, text: str) -> RfpPack:
        pack = await self.get(tenant, pack_id)
        if pack is None:
            raise RfpPackNotFound(pack_id)
        pack.document_text = text
        return pack

    async def set_outcome(self, tenant: str, pack_id: str, *, outcome: str | None,
                          reason: str, value: float | None) -> RfpPack:
        pack = await self.get(tenant, pack_id)
        if pack is None:
            raise RfpPackNotFound(pack_id)
        pack.outcome, pack.outcome_reason, pack.outcome_value = outcome, reason, value
        pack.outcome_at = _now() if outcome else None
        return pack

    async def set_brief(self, tenant: str, pack_id: str, brief: dict | None) -> RfpPack:
        pack = await self.get(tenant, pack_id)
        if pack is None:
            raise RfpPackNotFound(pack_id)
        pack.brief = brief
        return pack

    async def set_compliance(self, tenant: str, pack_id: str, items: list | None) -> RfpPack:
        pack = await self.get(tenant, pack_id)
        if pack is None:
            raise RfpPackNotFound(pack_id)
        pack.compliance = items
        return pack

    async def set_gen_status(self, tenant: str, pack_id: str, status: dict | None) -> RfpPack:
        pack = await self.get(tenant, pack_id)
        if pack is None:
            raise RfpPackNotFound(pack_id)
        pack.gen_status = status
        return pack

    async def delete(self, tenant: str, pack_id: str) -> None:
        packs = self._by_tenant.get(tenant, [])
        self._by_tenant[tenant] = [p for p in packs if p.id != pack_id]


@dataclass
class RfpPackService:
    store: RfpPackStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryRfpPackStore()

    async def create(self, tenant: str, agent_id: str, title: str, *,
                     client_name: str = "", deadline: str | None = None) -> RfpPack:
        pack = RfpPack(id=uuid.uuid4().hex[:12], tenant=tenant, agent_id=agent_id, title=title,
                       client_name=client_name, deadline=deadline)
        return await self.store.add(pack)

    async def list(self, tenant: str, *, agent_id: str | None = None) -> list[RfpPack]:
        return await self.store.list(tenant, agent_id=agent_id)

    async def get(self, tenant: str, pack_id: str) -> RfpPack:
        pack = await self.store.get(tenant, pack_id)
        if pack is None:
            raise RfpPackNotFound(pack_id)
        return pack

    async def set_stage(self, tenant: str, pack_id: str, stage: str) -> RfpPack:
        if stage not in STAGES:
            raise ValueError(f"invalid stage '{stage}', must be one of {STAGES}")
        return await self.store.set_stage(tenant, pack_id, stage)

    async def set_document_text(self, tenant: str, pack_id: str, text: str) -> RfpPack:
        return await self.store.set_document_text(tenant, pack_id, text)

    async def set_outcome(self, tenant: str, pack_id: str, *, outcome: str | None,
                          reason: str = "", value: float | None = None) -> RfpPack:
        if outcome is not None and outcome not in OUTCOMES:
            raise ValueError(f"invalid outcome '{outcome}', must be one of {OUTCOMES} (or null to clear)")
        if outcome == "lost" and reason and reason not in LOSS_REASONS:
            raise ValueError(f"invalid loss reason '{reason}', must be one of {LOSS_REASONS}")
        return await self.store.set_outcome(tenant, pack_id, outcome=outcome, reason=reason, value=value)

    async def set_brief(self, tenant: str, pack_id: str, brief: dict | None) -> RfpPack:
        return await self.store.set_brief(tenant, pack_id, brief)

    async def set_compliance(self, tenant: str, pack_id: str, items: list | None) -> RfpPack:
        return await self.store.set_compliance(tenant, pack_id, items)

    async def set_gen_status(self, tenant: str, pack_id: str, status: dict | None) -> RfpPack:
        return await self.store.set_gen_status(tenant, pack_id, status)

    async def stats(self, tenant: str, *, agent_id: str | None = None) -> dict:
        """Win/Loss Analysis rollup: win rate, total pipeline value, and a breakdown of why bids
        were lost -- the thing a sales lead actually wants after a quarter of tenders."""
        packs = await self.list(tenant, agent_id=agent_id)
        decided = [p for p in packs if p.outcome in ("won", "lost")]
        won = [p for p in decided if p.outcome == "won"]
        lost = [p for p in decided if p.outcome == "lost"]
        withdrawn = [p for p in packs if p.outcome == "withdrawn"]
        loss_reasons: dict[str, int] = {}
        for p in lost:
            key = p.outcome_reason or "unspecified"
            loss_reasons[key] = loss_reasons.get(key, 0) + 1
        return {
            "total_decided": len(decided),
            "won": len(won),
            "lost": len(lost),
            "withdrawn": len(withdrawn),
            "pending": len(packs) - len(decided) - len(withdrawn),
            "win_rate": round(len(won) / len(decided), 3) if decided else None,
            "won_value": sum(p.outcome_value or 0 for p in won),
            "lost_value": sum(p.outcome_value or 0 for p in lost),
            "loss_reasons": loss_reasons,
        }

    async def delete(self, tenant: str, pack_id: str) -> None:
        await self.store.delete(tenant, pack_id)


@dataclass
class PackRequirement:
    id: str
    tenant: str
    pack_id: str
    req_id: str
    title: str
    classification: str
    requirement: str


class RequirementStore(Protocol):
    async def replace_all(self, tenant: str, pack_id: str, items: list[PackRequirement]) -> list[PackRequirement]: ...
    async def list(self, tenant: str, pack_id: str) -> list[PackRequirement]: ...
    async def delete_for_pack(self, tenant: str, pack_id: str) -> None: ...


@dataclass
class InMemoryRequirementStore:
    _by_pack: dict[str, list[PackRequirement]] = field(default_factory=dict)

    async def replace_all(self, tenant: str, pack_id: str, items: list[PackRequirement]) -> list[PackRequirement]:
        self._by_pack[pack_id] = items
        return items

    async def list(self, tenant: str, pack_id: str) -> list[PackRequirement]:
        return [r for r in self._by_pack.get(pack_id, []) if r.tenant == tenant]

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        self._by_pack.pop(pack_id, None)


@dataclass
class CachedAnswer:
    pack_id: str
    req_id: str
    tenant: str
    answer: str
    confidence: float
    decision: str
    citations: list[str]
    note: str


class PackAnswerStore(Protocol):
    async def get_all(self, tenant: str, pack_id: str) -> dict[str, CachedAnswer]: ...
    async def put(self, tenant: str, pack_id: str, req_id: str, answer: CachedAnswer) -> None: ...
    async def delete_for_pack(self, tenant: str, pack_id: str) -> None: ...


@dataclass
class InMemoryPackAnswerStore:
    _by_pack: dict[str, dict[str, CachedAnswer]] = field(default_factory=dict)

    async def get_all(self, tenant: str, pack_id: str) -> dict[str, CachedAnswer]:
        return {k: v for k, v in self._by_pack.get(pack_id, {}).items() if v.tenant == tenant}

    async def put(self, tenant: str, pack_id: str, req_id: str, answer: CachedAnswer) -> None:
        self._by_pack.setdefault(pack_id, {})[req_id] = answer

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        self._by_pack.pop(pack_id, None)


@dataclass
class PackAnswerService:
    store: PackAnswerStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryPackAnswerStore()

    async def get_all(self, tenant: str, pack_id: str) -> dict[str, CachedAnswer]:
        return await self.store.get_all(tenant, pack_id)

    async def put(self, tenant: str, pack_id: str, req_id: str, answer: CachedAnswer) -> None:
        await self.store.put(tenant, pack_id, req_id, answer)

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        await self.store.delete_for_pack(tenant, pack_id)


@dataclass
class RequirementService:
    store: RequirementStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryRequirementStore()

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        await self.store.delete_for_pack(tenant, pack_id)

    async def save_extracted(self, tenant: str, pack_id: str, extracted: list[dict]) -> list[PackRequirement]:
        items = [
            PackRequirement(id=uuid.uuid4().hex[:12], tenant=tenant, pack_id=pack_id,
                            req_id=e["id"], title=e["title"], classification=e["classification"],
                            requirement=e["requirement"])
            for e in extracted
        ]
        return await self.store.replace_all(tenant, pack_id, items)

    async def list(self, tenant: str, pack_id: str) -> list[PackRequirement]:
        return await self.store.list(tenant, pack_id)
