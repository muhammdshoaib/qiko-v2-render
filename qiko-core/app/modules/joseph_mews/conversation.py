"""Joe's conversation turn: the generic Worker.answer() (grounded, gated) mapped to a WorkerReply
Interakt can actually act on.

Interakt cannot send free text (see channels/interakt.py): even an auto-accepted, well-grounded
answer cannot go straight to the customer as-is, so it is surfaced as a draft for a human agent to
review and send through Interakt's own inbox (matches why Interakt's own API exposes a Chat
Assignment endpoint). Automated template selection from Joe's free-text answer is a separate,
not-yet-built decision (JM2-1027): deliberately not guessed here, since auto-sending the wrong
template is worse than asking a human once.
"""

from __future__ import annotations

from app.modules.agentcore.models import AgentResult, Decision
from app.modules.channels.interakt import ReplyMode, WorkerReply
from app.modules.joseph_mews.qualification import FundingMethod, LeadQualification, Timeline, score
from app.modules.workers.worker import Worker, WorkerRecheck

# JM2-1031: RouteOutcome carries no priority of its own (it is a next-step, not an urgency
# label), so this is a separate, deliberately simple mapping from score() -- same spirit as
# qualification.py's own weights: a documented starting point, not a confirmed formula.
_HIGH_PRIORITY_SCORE = 60
_MEDIUM_PRIORITY_SCORE = 30


def _extracted_traits(qualification: LeadQualification) -> dict[str, object]:
    """Only what Joe actually learned -- an "unknown"/False field is Joe never having asked or
    the lead never having said, not a fact worth putting in front of a human agent."""
    traits: dict[str, object] = {}
    if qualification.timeline is not Timeline.unknown:
        traits["timeline"] = qualification.timeline.value
    if qualification.funding_method is not FundingMethod.unknown:
        traits["fundingMethod"] = qualification.funding_method.value
    if qualification.journey_stage:
        traits["journeyStage"] = qualification.journey_stage
    if qualification.has_budget_signal:
        traits["hasBudgetSignal"] = True
    if qualification.interest_signal:
        traits["interestSignal"] = True
    if qualification.other_factors:
        traits["otherFactors"] = qualification.other_factors
    return traits


def _priority_for(qualification: LeadQualification) -> str:
    points = score(qualification)
    if points >= _HIGH_PRIORITY_SCORE:
        return "high"
    if points >= _MEDIUM_PRIORITY_SCORE:
        return "medium"
    return "low"


def _next_action_for(qualification: LeadQualification) -> str:
    # route_outcome() is not useful here: qualification.wants_human is always True in this
    # branch (see to_worker_reply below), so it would always resolve to RouteOutcome.escalate
    # regardless of how qualified the lead otherwise is. score() alone is what actually
    # differentiates a highly-qualified lead asking for a person from one who is not.
    if score(qualification) >= _HIGH_PRIORITY_SCORE:
        return "Lead is ready to book - call to schedule a consultation and confirm details."
    return "Lead asked to speak with a person - review the conversation and reach out directly."


def to_worker_reply(result: AgentResult, qualification: LeadQualification | None = None) -> WorkerReply:
    # An explicit ask for a human (qualification.py's escalation signal, matching the client's own
    # escalation protocol) always wins, even over a well-grounded, auto-accepted answer: the lead
    # said they want a person, so drafting more AI text instead is the wrong call regardless of
    # how good that text is.
    if qualification is not None and qualification.wants_human:
        return WorkerReply(
            reply_mode=ReplyMode.handoff,
            handoff_reason="the lead asked for a human",
            handoff_reason_code="human_requested",
            handoff_extracted_traits=_extracted_traits(qualification),
            handoff_suggested_next_action=_next_action_for(qualification),
            handoff_priority=_priority_for(qualification),
        )
    if result.decision is Decision.human_review or result.stub:
        # No qualification here (e.g. the very first turn, or jm-backend/joseph-mews-backend was
        # unavailable for history -- see channels/router.py): report the gap honestly rather than
        # fabricate traits/priority Joe never actually gathered.
        return WorkerReply(
            reply_mode=ReplyMode.handoff,
            handoff_reason=result.gaps or "the gate escalated this turn for human review",
            handoff_reason_code="low_grounding",
            handoff_suggested_next_action=(
                "Joe could not answer confidently within approved knowledge - review the "
                "conversation and reply manually."
            ),
            handoff_priority="medium",
        )
    return WorkerReply(reply_mode=ReplyMode.draft_for_agent, draft_text=result.answer)


async def advance_turn(
    worker: Worker,
    conversation_id: str,
    message_text: str,
    *,
    history_context: list[str] | None = None,
    recheck_worker: WorkerRecheck | None = None,
    qualification: LeadQualification | None = None,
) -> WorkerReply:
    result = await worker.answer(
        conversation_id, message_text, additional_context=history_context, recheck_worker=recheck_worker
    )
    return to_worker_reply(result, qualification)
