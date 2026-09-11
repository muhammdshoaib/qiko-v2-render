"""Backward-compatible re-export shim.

`Pipeline` and `PipelineConfig` moved to app.modules.agentcore.orchestration.runner because they
are vertical-agnostic. Kept as a thin re-export here because this exact module path is still
imported directly (not just via this package's __init__) by app.modules.intelligence.research,
which also reaches into the private `_consolidated_from_dict` helper directly.
"""
from __future__ import annotations

from app.modules.agentcore.orchestration.models import PipelineRunStore  # noqa: F401
from app.modules.agentcore.orchestration.runner import (  # noqa: F401
    Pipeline,
    PipelineConfig,
    _consolidated_from_dict,
)

__all__ = ["Pipeline", "PipelineConfig", "PipelineRunStore"]
