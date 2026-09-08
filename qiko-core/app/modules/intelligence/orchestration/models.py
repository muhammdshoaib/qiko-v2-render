"""Backward-compatible re-export shim.

The generic pipeline models (PipelineRun, EvidenceBundle, SpecialistOutput, Finding,
ConsolidatedOutput, Verdict, the store protocol and its in-memory implementation) moved to
app.modules.agentcore.orchestration.models because they are vertical-agnostic. Kept as a thin
re-export here because this exact module path is still imported directly (not just via this
package's __init__) by app.modules.intelligence.research, app.modules.intelligence.backlog and
their tests.
"""
from __future__ import annotations

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

__all__ = [
    "ConsolidatedOutput",
    "EvidenceBundle",
    "Finding",
    "InMemoryPipelineRunStore",
    "PipelineRun",
    "PipelineRunStore",
    "SpecialistOutput",
    "Verdict",
]
