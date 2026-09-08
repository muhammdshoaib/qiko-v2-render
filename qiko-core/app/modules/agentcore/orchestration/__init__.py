"""Vertical-agnostic 5-role agentic pipeline core: Pipeline execution/persistence plus the three
roles (Synthesizer, Critic, Magistrate) that need no vertical-specific evidence source. Scout and
Specialist are per-vertical - see app.modules.intelligence.orchestration.roles and
app.modules.sales_intelligence.orchestration."""
from app.modules.agentcore.orchestration.models import (
    ConsolidatedOutput,
    EvidenceBundle,
    Finding,
    InMemoryPipelineRunStore,
    PipelineRun,
    PipelineRunStore,
    SpecialistOutput,
    Verdict,
)
from app.modules.agentcore.orchestration.roles import Critic, Magistrate, Synthesizer
from app.modules.agentcore.orchestration.runner import Pipeline, PipelineConfig

__all__ = [
    "ConsolidatedOutput",
    "Critic",
    "EvidenceBundle",
    "Finding",
    "InMemoryPipelineRunStore",
    "Magistrate",
    "Pipeline",
    "PipelineConfig",
    "PipelineRun",
    "PipelineRunStore",
    "SpecialistOutput",
    "Synthesizer",
    "Verdict",
]
