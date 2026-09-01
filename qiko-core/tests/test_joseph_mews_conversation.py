from app.modules.agentcore.models import AgentResult, Critique, Decision
from app.modules.channels.interakt import ReplyMode
from app.modules.joseph_mews.conversation import to_worker_reply


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
