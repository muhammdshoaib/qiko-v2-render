"""Research brief feature (QIW-1016).

A thin wrapper over the QIW-1014 orchestration pipeline that starts a research run,
renders the consolidated output as a reviewable brief, and accepts the brief into the
worker's knowledge corpus so it becomes retrievable ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.modules.intelligence.models import Signal, SignalStore
from app.modules.intelligence.orchestration.runner import Pipeline, PipelineConfig, PipelineRunStore
from app.modules.intelligence.orchestration.models import (
    ConsolidatedOutput,
    Finding,
    PipelineRun,
)
from app.modules.knowledge.service import KnowledgeService
from app.modules.workers.worker import Worker


BriefStatus = Literal["in_progress", "draft", "accepted"]


@dataclass
class Brief:
    run_id: str
    tenant: str
    agent_id: str
    subject: str
    status: BriefStatus
    summary: str
    findings: list[Finding]
    gaps: str
    citations: list[str]
    accepted_at: datetime | None = None


@dataclass
class ResearchService:
    store: PipelineRunStore
    knowledge: KnowledgeService
    signal_store: SignalStore
    worker: Worker | None = None

    async def start(
        self,
        tenant: str,
        agent_id: str,
        subject: str,
        facets: list[str],
    ) -> PipelineRun:
        config = PipelineConfig(
            tenant=tenant,
            agent_id=agent_id,
            subject=subject,
            facets=list(facets),
            kind="research",
        )
        run = Pipeline.new_run(config)
        await self.store.add(run)
        return run

    async def get_brief(self, tenant: str, agent_id: str, run_id: str) -> Brief | None:
        run = await self.store.get(tenant, agent_id, run_id)
        if run is None:
            return None
        return _build_brief(run)

    async def accept_brief(
        self,
        tenant: str,
        agent_id: str,
        run_id: str,
        *,
        actor: str,
    ) -> Brief | None:
        run = await self.store.get(tenant, agent_id, run_id)
        if run is None:
            return None
        brief = _build_brief(run)
        if brief.status == "accepted":
            return brief
        if brief.status == "in_progress":
            raise ValueError("run is not complete")

        text = _render_brief(brief)
        await self.knowledge.ingest(tenant, f"research:{run_id}", text, agent_id=agent_id)

        signal = Signal(
            tenant=tenant,
            agent_id=agent_id,
            source="research",
            kind="brief",
            external_id=run_id,
            container=run_id,
            actor=actor,
            title=brief.subject,
            body=text[:4000],
            occurred_at=datetime.now(timezone.utc),
            ref=None,
            tags=[],
        )
        await self.signal_store.add(signal)

        if self.worker is not None:
            await self.worker.approve(run_id, text, topic=brief.subject, agent_id=agent_id)

        brief_outputs = run.status.setdefault("outputs", {})
        brief_outputs["brief"] = {
            "accepted": True,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "text": text,
        }
        run.verdict = "accepted"
        await self.store.update(run)
        return _build_brief(run)


def _build_brief(run: PipelineRun) -> Brief:
    status: BriefStatus = "in_progress"
    summary = ""
    findings: list[Finding] = []
    citations: list[str] = []
    gaps = ""
    accepted_at: datetime | None = None

    if run.status and run.status.get("magistrate") == "ready":
        status = "draft"
        consolidated = _consolidated_from_run(run)
        summary = consolidated.text
        findings = list(consolidated.findings)
        citations = list(consolidated.citations)
        gaps = _build_gaps(consolidated, run)
        brief_output = (run.status.get("outputs") or {}).get("brief") or {}
        if brief_output.get("accepted"):
            status = "accepted"
            accepted_at_str = brief_output.get("accepted_at")
            if accepted_at_str:
                accepted_at = datetime.fromisoformat(accepted_at_str)

    return Brief(
        run_id=run.run_id,
        tenant=run.tenant,
        agent_id=run.agent_id,
        subject=run.subject,
        status=status,
        summary=summary,
        findings=findings,
        gaps=gaps,
        citations=citations,
        accepted_at=accepted_at,
    )


def _consolidated_from_run(run: PipelineRun) -> ConsolidatedOutput:
    from app.modules.intelligence.orchestration.runner import _consolidated_from_dict

    consolidated_data = ((run.status or {}).get("outputs") or {}).get("consolidated") or {}
    return _consolidated_from_dict(consolidated_data)


def _build_gaps(consolidated: ConsolidatedOutput, run: PipelineRun) -> str:
    parts: list[str] = []
    if consolidated.gaps:
        parts.append(consolidated.gaps)
    if not consolidated.text and not consolidated.findings:
        parts.append("No evidence found for the subject.")
    critique_data = ((run.status or {}).get("outputs") or {}).get("critique") or {}
    issues = critique_data.get("issues") or []
    for issue in issues:
        if issue:
            parts.append(f"Unsupported: {issue}")
    return "\n".join(parts)


def _render_brief(brief: Brief) -> str:
    lines: list[str] = [f"Subject: {brief.subject}", "", brief.summary, ""]
    if brief.findings:
        lines.append("Findings:")
        for finding in brief.findings:
            lines.append(f"- {finding.text}")
            if finding.evidence_refs:
                lines.append(f"  Evidence: {', '.join(finding.evidence_refs)}")
    if brief.gaps:
        lines.extend(["", "Gaps:", brief.gaps])
    return "\n".join(lines)
