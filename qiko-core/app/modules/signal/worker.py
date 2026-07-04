"""Signal worker vertical: a WorkerConfig over agentcore + the measurement firewall.

The firewall is the core Signal invariant: the agent PRESENTS engine output and must NEVER compute
or alter a score. Tier gating locks the Comparison bucket below the Specialist tier; scans are
authorised per-agent (BOLA).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.workers.config import WorkerConfig

# Tier order (low -> high). Comparison bucket unlocks at Specialist.
TIERS = ["starter", "growth", "specialist", "enterprise"]

_SIGNAL_PROMPT = (
    "You are a Qiko Signal AI-visibility worker. MEASUREMENT FIREWALL: you must ONLY present "
    "scores, buckets and recommendations returned by the Signal engine tools. You must NEVER "
    "compute, estimate, or alter a score yourself. If a number is not from the engine, do not state it."
)


class MeasurementFirewallError(Exception):
    pass


def signal_worker_config(tenant: str, *, gate_threshold: float = 0.85) -> WorkerConfig:
    return WorkerConfig(name=f"signal-{tenant}", tenant=tenant, gate_threshold=gate_threshold,
                        system_prompt=_SIGNAL_PROMPT)


def _tier_rank(tier: str) -> int:
    return TIERS.index(tier) if tier in TIERS else -1


def comparison_unlocked(tier: str) -> bool:
    return _tier_rank(tier) >= _tier_rank("specialist")


@dataclass
class SignalScan:
    scan_id: str
    agent_id: str
    engine_score: int


def authorize_scan(scan: SignalScan, requesting_agent_id: str) -> None:
    """BOLA: a scan may only be read by the agent it belongs to."""
    if scan.agent_id != requesting_agent_id:
        raise PermissionError("scan does not belong to this agent")


def verify_presented_score(engine_score: int, presented_score: int) -> int:
    """Firewall check: the score the agent presents MUST equal the engine's score."""
    if presented_score != engine_score:
        raise MeasurementFirewallError("presented score does not match the engine score")
    return presented_score
