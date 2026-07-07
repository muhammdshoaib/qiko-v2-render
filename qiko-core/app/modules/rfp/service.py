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


class RfpPackNotFound(Exception):
    pass


class RfpPackStore(Protocol):
    async def add(self, pack: RfpPack) -> RfpPack: ...
    async def list(self, tenant: str, *, agent_id: str | None = None) -> list[RfpPack]: ...
    async def get(self, tenant: str, pack_id: str) -> RfpPack | None: ...
    async def set_stage(self, tenant: str, pack_id: str, stage: str) -> RfpPack: ...
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


@dataclass
class InMemoryRequirementStore:
    _by_pack: dict[str, list[PackRequirement]] = field(default_factory=dict)

    async def replace_all(self, tenant: str, pack_id: str, items: list[PackRequirement]) -> list[PackRequirement]:
        self._by_pack[pack_id] = items
        return items

    async def list(self, tenant: str, pack_id: str) -> list[PackRequirement]:
        return [r for r in self._by_pack.get(pack_id, []) if r.tenant == tenant]


@dataclass
class RequirementService:
    store: RequirementStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryRequirementStore()

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
