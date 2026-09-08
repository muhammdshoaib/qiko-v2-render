from app.modules.agentcore.models import AgentResult, Critique, Decision
from app.modules.channels.interakt import ReplyMode
from app.modules.joseph_mews.conversation import to_worker_reply
from app.modules.joseph_mews.qualification import FundingMethod, LeadQualification, Timeline


def _result(*, decision: Decision, answer: str = "some grounded answer", stub: bool = False,
           gaps: str = "") -> AgentResult:
    return AgentResult(
        requirement_id="conv-1", answer=answer, critique=Critique(grounding=0.9),
        decision=decision, gaps=gaps, stub=stub,
    )


def test_human_review_decision_becomes_handoff():
    reply = to_worker_reply(_result(decision=Decision.human_review, gaps="not enough evidence"))
    assert reply.reply_mode == ReplyMode.handoff
    assert reply.handoff_reason == "not enough evidence"


def test_stub_provider_becomes_handoff_even_if_auto_accepted():
    reply = to_worker_reply(_result(decision=Decision.auto_accept, stub=True))
    assert reply.reply_mode == ReplyMode.handoff


def test_auto_accept_becomes_a_draft_for_a_human_to_send():
    """Interakt cannot send free text: even a well-grounded auto-accepted answer is never sent
    automatically, it is surfaced as a draft. Automated template selection is a separate,
    not-yet-built decision (JM2-1027)."""
    reply = to_worker_reply(_result(decision=Decision.auto_accept, answer="Manchester yields ~5.5-6.5%."))
    assert reply.reply_mode == ReplyMode.draft_for_agent
    assert reply.draft_text == "Manchester yields ~5.5-6.5%."


def test_human_review_without_gaps_gets_a_generic_reason():
    reply = to_worker_reply(_result(decision=Decision.human_review, gaps=""))
    assert reply.reply_mode == ReplyMode.handoff
    assert reply.handoff_reason


def test_wants_human_forces_handoff_even_over_a_grounded_auto_accepted_answer():
    result = _result(decision=Decision.auto_accept, answer="Manchester yields ~5.5-6.5%.")
    reply = to_worker_reply(result, qualification=LeadQualification(wants_human=True))
    assert reply.reply_mode == ReplyMode.handoff
    assert reply.handoff_reason == "the lead asked for a human"


def test_qualification_without_wants_human_does_not_change_the_outcome():
    result = _result(decision=Decision.auto_accept, answer="Manchester yields ~5.5-6.5%.")
    reply = to_worker_reply(result, qualification=LeadQualification(wants_human=False))
    assert reply.reply_mode == ReplyMode.draft_for_agent


def test_wants_human_handoff_carries_a_structured_packet():
    """JM2-1031: a bare handoff_reason string is not enough for a human agent to act on - the
    packet needs a short reason code, the traits Joe already extracted, a suggested next action
    and a priority, matching api-spec-whatsapp-joe-agent.md section 3.4."""
    result = _result(decision=Decision.auto_accept, answer="Manchester yields ~5.5-6.5%.")
    qualification = LeadQualification(
        wants_human=True, timeline=Timeline.soon, funding_method=FundingMethod.cash,
        journey_stage="experienced", has_budget_signal=True, interest_signal=True,
    )
    reply = to_worker_reply(result, qualification=qualification)
    assert reply.reply_mode == ReplyMode.handoff
    assert reply.handoff_reason_code == "human_requested"
    assert reply.handoff_extracted_traits == {
        "timeline": "soon", "fundingMethod": "cash", "journeyStage": "experienced",
        "hasBudgetSignal": True, "interestSignal": True,
    }
    assert reply.handoff_suggested_next_action == (
        "Lead is ready to book - call to schedule a consultation and confirm details."
    )
    assert reply.handoff_priority == "high"


def test_low_grounding_handoff_gets_a_reason_code_without_fabricated_traits():
    """No qualification passed (e.g. very first turn) -> the packet must not invent traits, just
    the reason code and a generic next action."""
    reply = to_worker_reply(_result(decision=Decision.human_review, gaps="not enough evidence"))
    assert reply.reply_mode == ReplyMode.handoff
    assert reply.handoff_reason_code == "low_grounding"
    assert reply.handoff_extracted_traits is None
    assert reply.handoff_suggested_next_action
    assert reply.handoff_priority == "medium"


def test_extracted_traits_omit_unknown_or_undetected_fields():
    """A packet listing every field as "unknown"/False is noise, not signal - only include what
    Joe actually learned."""
    result = _result(decision=Decision.auto_accept)
    qualification = LeadQualification(wants_human=True)  # everything else at its default
    reply = to_worker_reply(result, qualification=qualification)
    assert reply.handoff_extracted_traits == {}


def test_medium_score_qualification_handoff_gets_medium_priority():
    # funding_method (10) + interest_signal (15) + has_budget_signal (20) = 45: inside the
    # medium band (30-59), below the high threshold (60) that requires a soon timeline.
    result = _result(decision=Decision.auto_accept)
    qualification = LeadQualification(
        wants_human=True, timeline=Timeline.unknown, funding_method=FundingMethod.cash,
        interest_signal=True, has_budget_signal=True,
    )
    reply = to_worker_reply(result, qualification=qualification)
    assert reply.handoff_priority == "medium"
    assert reply.handoff_suggested_next_action == (
        "Lead asked to speak with a person - review the conversation and reach out directly."
    )


def test_zero_score_qualification_handoff_gets_low_priority():
    result = _result(decision=Decision.auto_accept)
    qualification = LeadQualification(wants_human=True, timeline=Timeline.unknown)
    reply = to_worker_reply(result, qualification=qualification)
    assert reply.handoff_priority == "low"
