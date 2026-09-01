from app.modules.joseph_mews.worker import TENANT, joseph_mews_worker_config


def test_config_is_scoped_to_the_joseph_mews_tenant():
    cfg = joseph_mews_worker_config()
    assert cfg.tenant == TENANT == "joseph-mews"


def test_prompt_enforces_english_only_regardless_of_lead_language():
    cfg = joseph_mews_worker_config()
    assert "ENGLISH ONLY" in cfg.system_prompt
    assert "regardless of the language" in cfg.system_prompt


def test_prompt_forbids_invented_facts_and_requires_escalation():
    cfg = joseph_mews_worker_config()
    assert "Never invent" in cfg.system_prompt
    assert "escalate" in cfg.system_prompt.lower()


def test_default_gate_threshold_matches_platform_default():
    from app.modules.agentcore.gate import DEFAULT_THRESHOLD

    cfg = joseph_mews_worker_config()
    assert cfg.gate_threshold == DEFAULT_THRESHOLD


def test_gate_threshold_is_overridable():
    cfg = joseph_mews_worker_config(gate_threshold=0.9)
    assert cfg.gate_threshold == 0.9
