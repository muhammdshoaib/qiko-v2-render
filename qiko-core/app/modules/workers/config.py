"""Worker configuration = the reusable structure.

A worker is NOT a bespoke codebase: it is a WorkerConfig over the shared agentcore + knowledge
engines. IDG pre-sales, Essential Living and Signal are instances of the same template, differing
only in config (tenant, knowledge, prompts, gate threshold, retrieval depth, region profile).

Note on terminology: this "template" is the reusable engine config, not the customer-facing
dashboard that the product elsewhere calls a "template". See the architecture uplift doc.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.agentcore.gate import DEFAULT_THRESHOLD


@dataclass(frozen=True)
class WorkerConfig:
    name: str
    tenant: str
    agent_id: str | None = None  # scopes this worker's knowledge retrieval/ingest to its own corpus
    gate_threshold: float = DEFAULT_THRESHOLD
    retrieval_k: int = 5
    system_prompt: str | None = None
    region_profile: str | None = None  # overrides the default Bedrock inference profile
