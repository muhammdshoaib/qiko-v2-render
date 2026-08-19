"""Pipeline runner: orchestrates the five roles, persists stage status after every step and is
resumable from a saved `PipelineRun` record.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.modules.agentcore.models import Critique
from app.modules.intelligence.orchestration.models import (
    ConsolidatedOutput,
    EvidenceBundle,
    Finding,
    PipelineRun,
    PipelineRunStore,
    SpecialistOutput,
    Verdict,
)
from app.modules.intelligence.orchestration.roles import (
    Critic,
    Magistrate,
    Scout,
    Specialist,
    Synthesizer,
)
from app.modules.workers.worker import StubProviderUnavailable

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initial_status(config: PipelineConfig) -> dict:
    return {
        "scout": "pending",
        "specialists": {
            "state": "pending",
            "done": 0,
            "total": 0,
            "failed": 0,
            "failed_ids": [],
        },
        "synthesize": "pending",
        "critic": "pending",
        "magistrate": "pending",
        "updated_at": _now_iso(),
        "error": None,
        "errors": {},
        "outputs": {},
        "revisions": 0,
        "config": dataclasses.asdict(config),
    }


def _stage_error(status: dict, stage: str, message: str) -> None:
    status["error"] = message
    status.setdefault("errors", {})[stage] = message


@dataclass
class PipelineConfig:
    tenant: str
    agent_id: str
    subject: str
    facets: list[str]
    max_facets: int = 5
    retry_limit: int = 1
    specialist_concurrency: int = 5

    def __post_init__(self) -> None:
        if len(self.facets) > self.max_facets:
            self.facets = self.facets[:self.max_facets]


class Pipeline:
    """Runs the agentic pipeline end to end and resumes from the store.

    A `Pipeline` instance is stateless; the mutable state for a single run lives in the
    `PipelineRun` record and is written to the store after each stage transition.
    """

    def __init__(
        self,
        *,
        scout: Scout,
        specialist: Specialist,
        synthesizer: Synthesizer,
        critic: Critic,
        magistrate: Magistrate,
        store: PipelineRunStore,
    ) -> None:
        self.scout = scout
        self.specialist = specialist
        self.synthesizer = synthesizer
        self.critic = critic
        self.magistrate = magistrate
        self.store = store

    async def start(self, config: PipelineConfig) -> PipelineRun:
        run_id = uuid.uuid4().hex
        run = PipelineRun(
            run_id=run_id,
            tenant=config.tenant,
            agent_id=config.agent_id,
            subject=config.subject,
            facets=list(config.facets),
            status=_initial_status(config),
        )
        await self.store.add(run)
        await self._execute(run)
        return run

    async def resume(self, tenant: str, agent_id: str, run_id: str) -> PipelineRun | None:
        run = await self.store.get(tenant, agent_id, run_id)
        if run is None:
            return None
        await self._execute(run)
        return run

    async def _save(self, run: PipelineRun) -> None:
        run.status["updated_at"] = _now_iso()
        await self.store.update(run)

    async def _execute(self, run: PipelineRun) -> None:
        config = PipelineConfig(**run.status["config"])

        while True:
            evidence = await self._scout_stage(run, config)
            if run.status["scout"] == "error":
                return

            outputs = await self._specialist_stage(run, config, evidence)
            if run.status["specialists"]["state"] == "error":
                return

            consolidated = await self._synthesize_stage(run, outputs)
            if run.status["synthesize"] == "error":
                return

            critique = await self._critic_stage(run, consolidated, evidence)
            if run.status["critic"] == "error":
                return

            verdict = await self._magistrate_stage(run, critique, config)
            if run.status["magistrate"] == "error":
                return

            if verdict.verdict == "revise" and run.status["revisions"] < config.retry_limit:
                run.status["revisions"] += 1
                run.status["outputs"]["revision_context"] = critique.issues
                run.status["outputs"].pop("specialist_outputs", None)
                run.status["outputs"].pop("consolidated", None)
                run.status["outputs"].pop("critique", None)
                run.status["outputs"].pop("verdict", None)
                run.status["specialists"] = {
                    "state": "pending",
                    "done": 0,
                    "total": 0,
                    "failed": 0,
                    "failed_ids": [],
                }
                run.status["synthesize"] = "pending"
                run.status["critic"] = "pending"
                run.status["magistrate"] = "pending"
                await self._save(run)
                continue
            return

    async def _scout_stage(self, run: PipelineRun, config: PipelineConfig) -> EvidenceBundle:
        if run.status["scout"] == "ready" and "evidence" in run.status["outputs"]:
            evidence = _evidence_from_dict(run.status["outputs"]["evidence"])
            revision_context = run.status["outputs"].get("revision_context", [])
            if revision_context and not _contains_all(evidence.text_chunks, revision_context):
                evidence = EvidenceBundle(
                    text_chunks=revision_context + evidence.text_chunks,
                    sources=evidence.sources,
                    signals=evidence.signals,
                    documents=evidence.documents,
                )
                run.status["outputs"]["evidence"] = _evidence_to_dict(evidence)
                await self._save(run)
            return evidence

        run.status["scout"] = "running"
        await self._save(run)
        context = list(run.status["outputs"].get("revision_context", []))
        try:
            evidence = await self.scout.gather(
                config.tenant, config.agent_id, config.subject, context=context)
        except Exception as exc:
            logger.exception("scout stage failed for %s/%s", config.tenant, config.agent_id)
            run.status["scout"] = "error"
            _stage_error(run.status, "scout", str(exc))
            await self._save(run)
            return EvidenceBundle()

        run.status["scout"] = "ready"
        run.status["outputs"]["evidence"] = _evidence_to_dict(evidence)
        await self._save(run)
        return evidence

    async def _specialist_stage(
        self, run: PipelineRun, config: PipelineConfig, evidence: EvidenceBundle,
    ) -> list[SpecialistOutput]:
        stage = run.status["specialists"]
        saved = run.status["outputs"].get("specialist_outputs")
        if stage["state"] in ("ready", "partial") and saved is not None:
            return [_specialist_output_from_dict(o) for o in saved]

        existing: list[SpecialistOutput] = []
        if stage["state"] == "running" and saved is not None:
            existing = [_specialist_output_from_dict(o) for o in saved]

        stage["state"] = "running"
        stage["total"] = len(config.facets)
        stage["done"] = len(existing)
        stage["failed"] = 0
        stage["failed_ids"] = []
        await self._save(run)

        completed_facets = {o.facet for o in existing}
        pending = [f for f in config.facets if f not in completed_facets]

        semaphore = asyncio.Semaphore(config.specialist_concurrency)
        outputs: list[SpecialistOutput] = list(existing)

        async def _work_one(facet: str) -> SpecialistOutput | None:
            async with semaphore:
                try:
                    out = await self.specialist.work(evidence, facet)
                except StubProviderUnavailable:
                    raise
                except Exception as exc:
                    logger.warning("specialist failed for facet %s: %s", facet, exc)
                    stage["failed"] += 1
                    failed_ids = list(stage["failed_ids"])
                    failed_ids.append(facet)
                    stage["failed_ids"] = failed_ids
                    await self._save(run)
                    return None
                outputs.append(out)
                stage["done"] += 1
                run.status["outputs"]["specialist_outputs"] = [dataclasses.asdict(o) for o in outputs]
                await self._save(run)
                return out

        try:
            results = await asyncio.gather(*[_work_one(f) for f in pending])
        except StubProviderUnavailable:
            stage["state"] = "error"
            _stage_error(run.status, "specialists", "answer generation is temporarily unavailable")
            await self._save(run)
            return outputs

        for out in results:
            if out is None:
                continue
            if out not in outputs:
                outputs.append(out)

        if stage["failed"] == 0:
            stage["state"] = "ready"
        else:
            stage["state"] = "partial"
        run.status["outputs"]["specialist_outputs"] = [dataclasses.asdict(o) for o in outputs]
        await self._save(run)
        return outputs

    async def _synthesize_stage(
        self, run: PipelineRun, outputs: list[SpecialistOutput],
    ) -> ConsolidatedOutput:
        if run.status["synthesize"] == "ready" and "consolidated" in run.status["outputs"]:
            return _consolidated_from_dict(run.status["outputs"]["consolidated"])

        run.status["synthesize"] = "running"
        await self._save(run)
        try:
            consolidated = await self.synthesizer.consolidate(outputs)
        except Exception as exc:
            logger.exception("synthesize stage failed")
            run.status["synthesize"] = "error"
            _stage_error(run.status, "synthesize", str(exc))
            await self._save(run)
            return ConsolidatedOutput(text="")

        run.status["synthesize"] = "ready"
        run.status["outputs"]["consolidated"] = dataclasses.asdict(consolidated)
        await self._save(run)
        return consolidated

    async def _critic_stage(
        self, run: PipelineRun, consolidated: ConsolidatedOutput, evidence: EvidenceBundle,
    ) -> Critique:
        if run.status["critic"] == "ready" and "critique" in run.status["outputs"]:
            return _critique_from_dict(run.status["outputs"]["critique"])

        run.status["critic"] = "running"
        await self._save(run)
        try:
            critique = await self.critic.score(consolidated, evidence)
        except Exception as exc:
            logger.exception("critic stage failed")
            run.status["critic"] = "error"
            _stage_error(run.status, "critic", str(exc))
            await self._save(run)
            return Critique(grounding=0.0, issues=[str(exc)])

        run.status["critic"] = "ready"
        run.status["outputs"]["critique"] = dataclasses.asdict(critique)
        await self._save(run)
        return critique

    async def _magistrate_stage(
        self, run: PipelineRun, critique: Critique, config: PipelineConfig,
    ) -> Verdict:
        if run.status["magistrate"] == "ready" and "verdict" in run.status["outputs"]:
            return _verdict_from_dict(run.status["outputs"]["verdict"])

        run.status["magistrate"] = "running"
        await self._save(run)
        try:
            verdict = self.magistrate.decide(critique)
        except Exception as exc:
            logger.exception("magistrate stage failed")
            run.status["magistrate"] = "error"
            _stage_error(run.status, "magistrate", str(exc))
            await self._save(run)
            return Verdict("escalate", str(exc), self.magistrate.threshold)

        run.status["magistrate"] = "ready"
        run.status["outputs"]["verdict"] = dataclasses.asdict(verdict)
        run.verdict = verdict.verdict
        await self._save(run)
        return verdict


def _contains_all(haystack: list[str], needles: list[str]) -> bool:
    return all(needle in haystack for needle in needles)


def _evidence_to_dict(evidence: EvidenceBundle) -> dict:
    return {
        "text_chunks": evidence.text_chunks,
        "sources": evidence.sources,
    }


def _evidence_from_dict(data: dict) -> EvidenceBundle:
    return EvidenceBundle(
        text_chunks=list(data.get("text_chunks") or []),
        sources=list(data.get("sources") or []),
    )


def _specialist_output_from_dict(data: dict) -> SpecialistOutput:
    return SpecialistOutput(
        facet=data["facet"],
        answer=data["answer"],
        confidence=data.get("confidence"),
        gaps=data.get("gaps", ""),
        citations=list(data.get("citations") or []),
    )


def _finding_from_dict(data: dict) -> Finding:
    return Finding(
        text=data.get("text") or "",
        confidence=data.get("confidence"),
        evidence_refs=list(data.get("evidence_refs") or []),
        gaps=data.get("gaps", ""),
    )


def _consolidated_from_dict(data: dict) -> ConsolidatedOutput:
    findings = [_finding_from_dict(f) for f in (data.get("findings") or [])]
    return ConsolidatedOutput(
        text=data.get("text") or "",
        findings=findings,
        citations=list(data.get("citations") or []),
        gaps=data.get("gaps", ""),
    )


def _critique_from_dict(data: dict) -> Critique:
    return Critique(
        grounding=float(data.get("grounding", 0.0)),
        issues=list(data.get("issues") or []),
    )


def _verdict_from_dict(data: dict) -> Verdict:
    return Verdict(
        verdict=data.get("verdict") or "escalate",
        reason=data.get("reason") or "",
        threshold=float(data.get("threshold", 0.0)),
    )
