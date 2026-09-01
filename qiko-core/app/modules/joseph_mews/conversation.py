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
from app.modules.joseph_mews.qualification import LeadQualification
from app.modules.workers.worker import Worker, WorkerRecheck


def to_worker_reply(result: AgentResult, qualification: LeadQualification | None = None) -> WorkerReply:
    # An explicit ask for a human (qualification.py's escalation signal, matching the client's own
    # escalation protocol) always wins, even over a well-grounded, auto-accepted answer: the lead
    # said they want a person, so drafting more AI text instead is the wrong call regardless of
    # how good that text is.
    if qualification is not None and qualification.wants_human:
        return WorkerReply(reply_mode=ReplyMode.handoff, handoff_reason="the lead asked for a human")
    if result.decision is Decision.human_review or result.stub:
        return WorkerReply(
            reply_mode=ReplyMode.handoff,
            handoff_reason=result.gaps or "the gate escalated this turn for human review",
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
