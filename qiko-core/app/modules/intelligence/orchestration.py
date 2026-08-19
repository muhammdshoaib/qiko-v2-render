"""Orchestrated agentic pipeline for the Intelligence Worker.

This module holds the domain model and the store protocol for pipeline runs.
The role implementations and runner arrive in later milestones.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


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
