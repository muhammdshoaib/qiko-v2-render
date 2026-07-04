import pytest

from app.modules.signal.worker import (
    MeasurementFirewallError,
    SignalScan,
    authorize_scan,
    comparison_unlocked,
    signal_worker_config,
    verify_presented_score,
)


def test_signal_config_has_firewall_prompt():
    cfg = signal_worker_config("idg")
    assert cfg.tenant == "idg" and "MEASUREMENT FIREWALL" in cfg.system_prompt
    assert "NEVER compute" in cfg.system_prompt


def test_tier_gating_comparison_bucket():
    assert comparison_unlocked("starter") is False
    assert comparison_unlocked("growth") is False
    assert comparison_unlocked("specialist") is True
    assert comparison_unlocked("enterprise") is True


def test_scan_bola_authorization():
    scan = SignalScan("s1", agent_id="agent-a", engine_score=72)
    authorize_scan(scan, "agent-a")  # ok
    with pytest.raises(PermissionError):
        authorize_scan(scan, "agent-b")  # not their scan


def test_measurement_firewall_rejects_altered_score():
    assert verify_presented_score(72, 72) == 72          # presenting engine output is allowed
    with pytest.raises(MeasurementFirewallError):
        verify_presented_score(72, 95)                    # agent fabricated/altered a score
