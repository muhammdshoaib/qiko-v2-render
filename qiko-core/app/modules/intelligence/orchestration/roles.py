"""Five-role agentic pipeline for the Intelligence Worker.

Scout, Specialist, Synthesizer, Critic and Magistrate. Each role is stateless; all mutable
state lives in the PipelineRun record managed by the runner (Milestone 3).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

from app.modules.agentcore import critic as critic_mod
from app.modules.agentcore import gate as gate_mod
from app.modules.agentcore.generator import Generator
from app.modules.agentcore.models import Critique, Decision, Requirement
from app.modules.ai.gateway import LLMProvider
from app.modules.intelligence.documents import DocumentStore
from app.modules.intelligence.models import SignalStore
from app.modules.intelligence.orchestration.models import (
    ConsolidatedOutput,
    EvidenceBundle,
    Finding,
    SpecialistOutput,
    Verdict,
)
from app.modules.knowledge.service import KnowledgeService
from app.modules.workers.worker import Worker

logger = logging.getLogger(__name__)

DEFAULT_RETRIEVAL_K = 5
DEFAULT_SIGNAL_LIMIT = 50
SPECIALIST_CONCURRENCY = 5

# Synthesizer prompt: ask for a JSON object with summary, findings and citations.
_SYNTHESIZER_SYSTEM = (
    "You are synthesizing parallel specialist outputs into one consolidated view. "
    "Use ONLY the evidence supplied in the CONTEXT. "
    "Return a single JSON object with keys: "
    '"summary" (a short prose summary), '
    '"findings" (a list of objects each with "text", optionally "gaps", '
    'and "evidence_refs" listing the source labels that support it), '
    '"citations" (a list of source labels). '
    "Do not invent facts, dates, names or figures. "
    "If the context contains no relevant evidence, set summary to "
    "\"I don't have that data.\" and findings to []."
)

# LLM critic prompt: the model may only LOWER the deterministic grounding score or add issues.
_LLM_CRITIC_SYSTEM = (
    "You are an independent grounding critic. Given a PROPOSED TEXT and a list of EVIDENCE, "
    "return a single JSON object with keys: "
    '"grounding" (a number 0..1, never higher than the evidence supports), '
    '"issues" (a list of unsupported or questionable sentences/phrases). '
    "If the text is fully supported, return grounding 1.0 and issues []."
)


class Scout:
    """Read-only evidence gathering. No LLM calls."""

    def __init__(
        self,
        knowledge: KnowledgeService,
        *,
        signal_store: SignalStore | None = None,
        document_store: DocumentStore | None = None,
        retrieval_k: int = DEFAULT_RETRIEVAL_K,
        signal_limit: int = DEFAULT_SIGNAL_LIMIT,
    ) -> None:
        self.knowledge = knowledge
        self.signal_store = signal_store
        self.document_store = document_store
        self.retrieval_k = retrieval_k
        self.signal_limit = signal_limit

    async def gather(
        self, tenant: str, agent_id: str, subject: str, *,
        context: list[str] | None = None,
    ) -> EvidenceBundle:
        text_chunks: list[str] = list(context or [])
        sources: list[str] = []

        passages = await self.knowledge.retrieve(
            tenant, subject, k=self.retrieval_k, agent_id=agent_id)
        text_chunks.extend([p.text for p in passages])
        sources.extend([p.doc_id for p in passages])

        signals: list = []
        if self.signal_store is not None:
            signals = await self.signal_store.list_recent(tenant, agent_id, limit=self.signal_limit)
            for s in signals:
                text_chunks.append(f"[{s.source}] {s.title}: {s.body}")
                sources.append(s.url or f"{s.source}:{s.external_id}")

        documents: list = []
        if self.document_store is not None:
            documents = await self.document_store.list(tenant, agent_id)
            for d in documents:
                text_chunks.append(f"[upload] {d.filename} ({d.status})")
                sources.append(d.doc_id)

        return EvidenceBundle(
            text_chunks=text_chunks,
            sources=_dedupe(sources),
            signals=signals,
            documents=documents,
        )


@dataclass
class Specialist:
    """One domain lens over an EvidenceBundle. Wraps the shared Worker/agentcore path."""

    worker: Worker

    async def work(self, bundle: EvidenceBundle, facet: str) -> SpecialistOutput:
        requirement_id = f"facet-{facet.replace(' ', '_').lower()[:32]}"
        text = f"Answer the following facet about the subject: {facet}"
        result = await self.worker.answer(
            requirement_id,
            text,
            topic=facet,
            additional_context=bundle.text_chunks,
        )
        return SpecialistOutput(
            facet=facet,
            answer=result.answer,
            confidence=result.confidence,
            gaps=result.gaps,
            citations=list(result.citations),
        )


class Synthesizer:
    """Consolidate parallel SpecialistOutput instances into one ConsolidatedOutput."""

    def __init__(self, generator: Generator) -> None:
        self.generator = generator

    async def consolidate(self, outputs: list[SpecialistOutput]) -> ConsolidatedOutput:
        if not outputs:
            return ConsolidatedOutput(text="")

        context: list[str] = []
        all_citations: list[str] = []
        for out in outputs:
            context.append(f"Facet: {out.facet}")
            context.append(f"Answer: {out.answer}")
            if out.gaps:
                context.append(f"Gaps: {out.gaps}")
            all_citations.extend(out.citations)

        req = Requirement(
            id="synthesize",
            text="Synthesize the specialist outputs in the CONTEXT into a consolidated view.",
            context=context,
        )
        prompt = self.generator.build_prompt(req)
        response = await asyncio.to_thread(
            self.generator.provider.generate,
            prompt,
            system=_SYNTHESIZER_SYSTEM,
            prefill="{",
        )
        parsed = _parse_synthesis(response.text)
        if parsed is None:
            return ConsolidatedOutput(
                text=response.text.strip(),
                citations=_dedupe(all_citations),
            )
        parsed.citations = _dedupe(parsed.citations + all_citations)
        return parsed


class Critic:
    """Deterministic grounding first; an optional LLM layer may only lower or add issues."""

    def __init__(
        self,
        *,
        llm_layer: LLMProvider | None = None,
        min_sentence_support: float = 0.6,
    ) -> None:
        self.llm_layer = llm_layer
        self.min_sentence_support = min_sentence_support

    async def score(self, output: ConsolidatedOutput, evidence: EvidenceBundle) -> Critique:
        base = critic_mod.grounding_score(
            output.text, evidence.text_chunks,
            min_sentence_support=self.min_sentence_support)
        if self.llm_layer is None:
            return base
        llm_critique = await self._llm_critique(output, evidence)
        if llm_critique is None:
            return base
        # The LLM layer is never allowed to raise the deterministic floor.
        grounding = min(base.grounding, llm_critique.grounding)
        issues = list(base.issues)
        seen = set(issues)
        for issue in llm_critique.issues:
            if issue and issue not in seen:
                seen.add(issue)
                issues.append(issue)
        return Critique(grounding=round(grounding, 3), issues=issues)

    async def _llm_critique(self, output: ConsolidatedOutput, evidence: EvidenceBundle) -> Critique | None:
        evidence_block = "\n".join(f"- {chunk}" for chunk in evidence.text_chunks) or "(none)"
        prompt = (
            f"PROPOSED TEXT:\n{output.text}\n\n"
            f"EVIDENCE:\n{evidence_block}\n\n"
            "Return ONLY a JSON object with keys \"grounding\" and \"issues\"."
        )
        try:
            response = await asyncio.to_thread(
                self.llm_layer.generate,
                prompt,
                system=_LLM_CRITIC_SYSTEM,
                prefill="{",
            )
        except Exception:
            logger.exception("LLM critic failed; falling back to deterministic score")
            return None
        return _parse_critique(response.text)


class Magistrate:
    """Gate with a revise band between accept and escalate."""

    REVISE_MARGIN = 0.1

    def __init__(self, threshold: float = gate_mod.DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold

    def decide(self, critique: Critique) -> Verdict:
        decision = gate_mod.decide(critique, threshold=self.threshold)
        if decision == Decision.auto_accept:
            return Verdict(
                verdict="accept",
                reason=f"grounding {critique.grounding} clears threshold {self.threshold}",
                threshold=self.threshold,
            )
        if critique.grounding >= self.threshold - self.REVISE_MARGIN and critique.issues:
            return Verdict(
                verdict="revise",
                reason=(
                    f"grounding {critique.grounding} is within {self.REVISE_MARGIN} of threshold "
                    f"and {len(critique.issues)} issue(s) look fixable"
                ),
                threshold=self.threshold,
            )
        return Verdict(
            verdict="escalate",
            reason=f"grounding {critique.grounding} is too far below threshold {self.threshold}",
            threshold=self.threshold,
        )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _parse_synthesis(text: str) -> ConsolidatedOutput | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else raw
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    summary = str(data.get("summary") or "").strip()
    if not summary:
        return None
    findings_data = data.get("findings") or []
    findings: list[Finding] = []
    if isinstance(findings_data, list):
        for item in findings_data:
            if isinstance(item, dict):
                refs = item.get("evidence_refs") or []
                if not isinstance(refs, list):
                    refs = []
                findings.append(Finding(
                    text=str(item.get("text") or ""),
                    gaps=str(item.get("gaps") or ""),
                    evidence_refs=[str(r) for r in refs if r],
                ))
    citations = [str(c) for c in data.get("citations") or [] if c]
    return ConsolidatedOutput(
        text=summary,
        findings=findings,
        citations=citations,
    )


def _parse_critique(text: str) -> Critique | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    grounding_raw = data.get("grounding")
    try:
        grounding = float(grounding_raw) if grounding_raw is not None else 0.0
    except (ValueError, TypeError):
        grounding = 0.0
    grounding = max(0.0, min(1.0, grounding))
    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    return Critique(
        grounding=round(grounding, 3),
        issues=[str(i) for i in issues if i],
    )
