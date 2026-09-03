from app.modules.joseph_mews.guardrails import SHARED_GUARDRAILS, resolve_guardrails


def test_resolve_guardrails_falls_back_to_shared_default_when_no_agent_config():
    assert resolve_guardrails(None) == SHARED_GUARDRAILS


def test_resolve_guardrails_falls_back_when_agent_config_has_no_behavior_entries():
    assert resolve_guardrails({}) == SHARED_GUARDRAILS
    assert resolve_guardrails({"tone": "friendly"}) == SHARED_GUARDRAILS


def test_resolve_guardrails_uses_the_agents_own_guardrails_when_set():
    result = resolve_guardrails({"guardrails": ["Never mention a competitor by name."]})
    assert "Never mention a competitor by name." in result
    assert result != SHARED_GUARDRAILS


def test_resolve_guardrails_includes_rules_and_prompts_too():
    result = resolve_guardrails({
        "prompts": ["Always sign off with the investor's first name."],
        "rules": ["Keep responses under 3 sentences."],
        "guardrails": ["Never mention a competitor by name."],
    })
    assert "Always sign off with the investor's first name." in result
    assert "Keep responses under 3 sentences." in result
    assert "Never mention a competitor by name." in result
