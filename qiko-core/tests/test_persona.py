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


def test_behavior_entries_support_legacy_strings_and_canonical_objects():
    p = synthesize_persona({
        "prompts": "Greet every customer by name.",
        "rules": [
            "Confirm what the customer needs before answering.",
            {"id": "rule-escalation", "title": "Escalation", "content": "Escalate refund requests."},
        ],
        "guardrails": [
            {"id": "guardrail-pii", "title": "Personal data", "content": "Never expose personal data."},
        ],
    })

    assert p is not None
    assert "Prompts:" in p and "Greet every customer by name." in p
    assert "Rules:" in p and "Confirm what the customer needs before answering." in p
    assert "Escalation" in p and "Escalate refund requests." in p
    assert "Guardrails:" in p and "Personal data" in p and "Never expose personal data." in p
    assert "rule-escalation" not in p and "guardrail-pii" not in p
    assert "{'id':" not in p and "['" not in p


def test_empty_behavior_arrays_do_not_create_a_persona():
    assert synthesize_persona({"prompts": [], "rules": [], "guardrails": []}) is None


def test_oversized_legacy_behavior_is_not_added_to_the_prompt():
    assert synthesize_persona({"rules": ["x" * 4001]}) is None
