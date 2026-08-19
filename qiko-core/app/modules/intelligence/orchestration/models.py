"""Domain models and the store protocol for the Intelligence Worker pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from app.modules.intelligence.documents import Document
from app.modules.intelligence.models import Signal


@dataclass
class PipelineRun:
    run_id: str
    tenant: str
    agent_id: str
    subject: str
    facets: list[str] = field(default_factory=list)
    status: dict | None = None
    verdict: str | None = None
    cost: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@runtime_checkable
class PipelineRunStore(Protocol):
    async def add(self, run: PipelineRun) -> None: ...
    async def get(self, tenant: str, agent_id: str, run_id: str) -> PipelineRun | None: ...
    async def list(self, tenant: str, agent_id: str) -> list[PipelineRun]: ...
    async def update(self, run: PipelineRun) -> None: ...


@dataclass
class InMemoryPipelineRunStore:
    """In-memory store for tests and dev mode."""

    _runs: dict[tuple[str, str, str], PipelineRun] = field(default_factory=dict)

    async def add(self, run: PipelineRun) -> None:
        key = (run.tenant, run.agent_id, run.run_id)
        now = datetime.now(timezone.utc)
        if run.created_at is None:
            run.created_at = now
        if run.updated_at is None:
            run.updated_at = now
        self._runs[key] = run

    async def get(self, tenant: str, agent_id: str, run_id: str) -> PipelineRun | None:
        return self._runs.get((tenant, agent_id, run_id))

    async def list(self, tenant: str, agent_id: str) -> list[PipelineRun]:
        def _sort_key(run: PipelineRun) -> datetime:
            return run.updated_at or run.created_at or datetime.min.replace(tzinfo=timezone.utc)

        return sorted(
            (r for r in self._runs.values() if r.tenant == tenant and r.agent_id == agent_id),
            key=_sort_key,
            reverse=True,
        )

    async def update(self, run: PipelineRun) -> None:
        key = (run.tenant, run.agent_id, run.run_id)
        if key not in self._runs:
            raise KeyError(run.run_id)
        run.updated_at = datetime.now(timezone.utc)
        self._runs[key] = run


@dataclass
class EvidenceBundle:
    """Evidence gathered by the Scout for downstream roles.

    `text_chunks` is what the specialist and critic see as grounding evidence.
    `sources` are short citation labels the UI can enumerate.
    """

    text_chunks: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)


@dataclass
class SpecialistOutput:
    facet: str
    answer: str
    confidence: float | None
    gaps: str
    citations: list[str] = field(default_factory=list)


@dataclass
class Finding:
    text: str
    confidence: float | None = None
    evidence_refs: list[str] = field(default_factory=list)
    gaps: str = ""


@dataclass
class ConsolidatedOutput:
    text: str
    findings: list[Finding] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    gaps: str = ""


@dataclass
class Verdict:
    verdict: str  # "accept" | "revise" | "escalate"
    reason: str
    threshold: float
