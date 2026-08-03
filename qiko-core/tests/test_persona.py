from app.modules.workers.persona import synthesize_persona


def test_empty_config_returns_none():
    assert synthesize_persona({}) is None
    assert synthesize_persona({"gate_threshold": 0.5, "retrieval_k": 8}) is None


def test_builds_identity_from_fields():
    p = synthesize_persona({"full_name": "Ava", "title": "Support Lead",
                            "expertise": "billing", "tone": "friendly",
                            "rules": "never share PII", "guardrails": "no legal advice"})
    assert p is not None
    assert p.startswith("You are Ava, Support Lead.")
    assert "billing" in p and "friendly" in p and "never share PII" in p and "no legal advice" in p
    assert "ONLY the supplied evidence" in p  # grounding rule preserved


def test_partial_config_no_name():
    p = synthesize_persona({"expertise": "logistics"})
    assert p is not None and p.startswith("You are a helpful AI assistant.") and "logistics" in p


def test_title_only_no_name_grammar():
    p = synthesize_persona({"title": "Support Lead"})
    assert p is not None and p.startswith("You are Support Lead.")  # no stray comma
