"""Intelligence Worker chat: answer questions grounded in captured signals.

Follows the pattern in app.modules.finance.chat but sits on top of the shared Worker
(agentcore + knowledge) so grounding, citations, cost caps and the flywheel all come for free.
"""
from __future__ import annotations

import uuid

from collections.abc import Awaitable, Callable

from app.modules.agentcore.models import AgentResult
from app.modules.chat.service import ChatService
from app.modules.workers.worker import StubProviderUnavailable, Worker

_GREETINGS = ("hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings")
_CAPABILITY = ("what can you do", "help", "capabilities", "what do you do", "how can you help")
_SPRINT_LANDING_QUESTIONS = (
    "is this sprint going to land",
    "will this sprint land",
    "is the sprint going to land",
    "will the sprint land",
    "sprint going to land",
    "sprint on track",
    "is the sprint on track",
    "will the sprint finish",
    "is the sprint going to finish",
)
_PROJECT_ACTIVITY_QUESTIONS = (
    "most active project",
    "most active",
    "active project",
    "busiest project",
    "cel mai activ proiect",
    "activ proiect",
    "proiect activ",
    "cel mai ocupat",
)
_LIST_PROJECTS_QUESTIONS = (
    "projects in qiko track",
    "proiecte în qiko track",
    "qiko track projects",
    "proiecte qiko track",
    "ce proiecte",
    "what projects",
    "list projects",
    "avem proiecte",
)
_QIKO_TRACK_ACCESS_KEYWORDS = ("access", "acces", "connected", "conectat", "reachable", "reach", "conectare")

_INTELLIGENCE_PROMPT = (
    "You are a Qiko Intelligence Worker. Answer ONLY using the signals in the CONTEXT below. "
    "Each signal is a captured message or event with a source URL. "
    "Cite the source URL for each claim you make. "
    "Never invent facts, dates, names, or figures. "
    "If the CONTEXT contains no relevant signal, say exactly: 'I don't have that data.'"
)

_NO_DATA_REPLY = "I don't have that data."


def _classify_intent(message: str) -> str:
    m = (message or "").strip().lower()
    if not m:
        return "general"
    if any(m == g or m.startswith(g + " ") or m.startswith(g + "!") for g in _GREETINGS):
        return "greeting"
    if any(phrase in m for phrase in _CAPABILITY):
        return "capability"
    if any(phrase in m for phrase in _SPRINT_LANDING_QUESTIONS):
        return "sprint_landing"
    if any(phrase in m for phrase in _PROJECT_ACTIVITY_QUESTIONS):
        return "project_activity"
    if any(phrase in m for phrase in _LIST_PROJECTS_QUESTIONS) or (
        ("projects" in m or "proiecte" in m) and "qiko track" in m
    ):
        return "list_projects"
    if "qiko track" in m and any(kw in m for kw in _QIKO_TRACK_ACCESS_KEYWORDS):
        return "qiko_track_access"
    return "data"


def _format_sprint_answer(projects: dict[str, dict]) -> str:
    """Build a grounded, non-opinionated answer to "is this sprint going to land?".

    Uses committed-versus-done from the active sprint. If there is no active
    sprint or the sprint lacks the end date needed for remaining days, decline
    honestly instead of guessing.
    """
    active: tuple[str, dict] | None = None
    for key, data in projects.items():
        sprint = data.get("sprint") or {}
        if sprint.get("state") == "active" and data.get("available") is True:
            active = (key, data)
            break

    if active is None:
        # No active sprint at all; look for any sprint data to report.
        for key, data in projects.items():
            if data.get("available") is True and data.get("sprint"):
                active = (key, data)
                break

    if active is None:
        return _NO_DATA_REPLY

    project_key, data = active
    sprint = data["sprint"]
    committed = sprint.get("committed") or {}
    done = sprint.get("done") or {}
    carry = sprint.get("projectedCarryOver") or {}

    committed_tickets = committed.get("tickets", 0)
    done_tickets = done.get("tickets", 0)
    carry_tickets = carry.get("tickets", 0)

    if committed_tickets == 0:
        return f"{project_key} sprint '{sprint.get('name')}' has no committed tickets."

    # The Qiko Track metrics endpoint does not expose a sprint end date, so we
    # cannot compute remaining days. Degrade honestly rather than inventing a
    # landing prediction.
    return (
        f"{project_key} sprint '{sprint.get('name')}' has "
        f"{done_tickets} of {committed_tickets} committed tickets done; "
        f"{carry_tickets} are projected to carry over. "
        "I don't have the sprint end date, so I can't say if it will land."
    )


def _format_project_activity_answer(projects: dict[str, dict]) -> str:
    """Build a grounded answer to "which is the most active project?".

    Uses Qiko Track project metrics. If no project has completed or in-progress
    tickets, decline honestly.
    """
    available = {k: v for k, v in projects.items() if v.get("available") is True}
    if not available:
        return _NO_DATA_REPLY

    by_throughput = sorted(
        available.items(),
        key=lambda kv: (kv[1].get("throughput") or {}).get("tickets", 0),
        reverse=True,
    )
    top_key, top_data = by_throughput[0]
    throughput = top_data.get("throughput") or {}
    wip = top_data.get("wip") or {}
    completed = throughput.get("tickets", 0)
    points = throughput.get("points", 0)
    in_progress = wip.get("total", 0)

    if completed > 0:
        return (
            f"{top_key} is the most active Qiko Track project, with {completed} completed tickets "
            f"in the last 30 days ({points} points) and {in_progress} ticket(s) in progress."
        )

    by_wip = sorted(
        available.items(),
        key=lambda kv: (kv[1].get("wip") or {}).get("total", 0),
        reverse=True,
    )
    top_key, top_data = by_wip[0]
    wip = top_data.get("wip") or {}
    if wip.get("total", 0) > 0:
        return (
            f"{top_key} has the most active work in progress ({wip['total']} tickets), "
            "though no tickets were completed in the last 30 days."
        )

    return _NO_DATA_REPLY


def _format_project_list_answer(projects: dict[str, dict]) -> str:
    """Build a grounded answer to "which Qiko Track projects do we have?".

    Lists available projects by key. If none are reachable, reports the
    configured keys and the reachability failure honestly.
    """
    if not projects:
        return _NO_DATA_REPLY
    available = {k: v for k, v in projects.items() if v.get("available") is True}
    if not available:
        keys = ", ".join(projects.keys())
        return f"I see the configured Qiko Track projects ({keys}) but cannot reach Qiko Track right now."
    keys = ", ".join(available.keys())
    count = len(available)
    return f"You have {count} Qiko Track project{'s' if count != 1 else ''}: {keys}."


def _format_qiko_track_access_answer(projects: dict[str, dict]) -> str:
    """Build a grounded answer to "do you have access to Qiko Track?".

    Answers yes/no based on whether the agent can reach any configured Qiko Track
    project right now, and lists the reachable project keys when it can.
    """
    if not projects:
        return _NO_DATA_REPLY
    available = {k: v for k, v in projects.items() if v.get("available") is True}
    if not available:
        keys = ", ".join(projects.keys())
        return f"Qiko Track is configured for {keys}, but I cannot reach it right now."
    keys = ", ".join(available.keys())
    count = len(available)
    return f"Yes. I can read Qiko Track data for {count} project{'s' if count != 1 else ''}: {keys}."


def _format_sources(result: AgentResult, passages: list) -> list[str]:
    """Return clickable source URLs, dropping empty or non-URL labels."""
    seen: set[str] = set()
    sources: list[str] = []
    for label in result.citations:
        url = (label or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        # The knowledge doc_id is the Slack permalink when available, otherwise source:external_id.
        if url.startswith("http://") or url.startswith("https://"):
            sources.append(url)
    return sources


class IntelligenceChat:
    """Chat over a worker's signal knowledge."""

    def __init__(self, worker: Worker, *, system_prompt: str | None = None) -> None:
        self.worker = worker
        # Override the default persona with the intelligence-specific grounding rule.
        self.system_prompt = system_prompt or _INTELLIGENCE_PROMPT
        self.worker.agent.generator.system_prompt = self.system_prompt

    async def answer(
        self, question: str, *, conversation_id: str | None = None,
        chat: ChatService | None = None, user_id: str = "public",
        metrics_provider: Callable[[], Awaitable[dict[str, dict]]] | None = None,
    ) -> dict:
        """Answer a question, record the exchange, and return sources.

        Returns a stable JSON shape whether the model is called or not, so the UI never has to
        special-case a greeting.
        """
        intent = _classify_intent(question)
        conversation_id = conversation_id or str(uuid.uuid4().hex[:16])
        tenant = self.worker.config.tenant
        agent_id = self.worker.config.agent_id or ""

        if intent == "greeting":
            reply = ("Hello! I'm your Intelligence Worker. Ask me about anything captured from "
                     "your connected sources, like Slack messages, GitHub activity, or tickets.")
            return await self._record_and_return(
                chat, tenant, conversation_id, user_id, agent_id, question, reply, intent)

        if intent == "capability":
            reply = ("I answer questions grounded in the signals your worker has captured. "
                     "I can quote messages, cite the original source link, and tell you when I "
                     "don't have supporting data.")
            return await self._record_and_return(
                chat, tenant, conversation_id, user_id, agent_id, question, reply, intent)

        if intent == "sprint_landing":
            if metrics_provider is None:
                reply = _NO_DATA_REPLY
            else:
                projects = await metrics_provider()
                reply = _format_sprint_answer(projects)
            return await self._record_and_return(
                chat, tenant, conversation_id, user_id, agent_id, question, reply, intent)

        if intent == "project_activity":
            if metrics_provider is None:
                reply = _NO_DATA_REPLY
            else:
                projects = await metrics_provider()
                reply = _format_project_activity_answer(projects)
                if "github" in question.lower() and "Qiko Track" in reply:
                    reply += " I don't have GitHub project activity data."
            return await self._record_and_return(
                chat, tenant, conversation_id, user_id, agent_id, question, reply, intent)

        if intent == "list_projects":
            if metrics_provider is None:
                reply = _NO_DATA_REPLY
            else:
                projects = await metrics_provider()
                reply = _format_project_list_answer(projects)
            return await self._record_and_return(
                chat, tenant, conversation_id, user_id, agent_id, question, reply, intent)

        if intent == "qiko_track_access":
            if metrics_provider is None:
                reply = _NO_DATA_REPLY
            else:
                projects = await metrics_provider()
                reply = _format_qiko_track_access_answer(projects)
            return await self._record_and_return(
                chat, tenant, conversation_id, user_id, agent_id, question, reply, intent)

        # Check retrieval before spending on a model call: a question with no supporting signal
        # must fail closed into an honest "I don't have that data" rather than a hallucinated answer.
        passages = await self.worker.knowledge.retrieve(
            tenant, question, k=self.worker.config.retrieval_k, agent_id=agent_id)
        if not passages:
            return await self._record_and_return(
                chat, tenant, conversation_id, user_id, agent_id, question, _NO_DATA_REPLY, intent)

        try:
            result = await self.worker.answer(conversation_id, question)
        except StubProviderUnavailable:
            return await self._record_and_return(
                chat, tenant, conversation_id, user_id, agent_id, question,
                "AI service is unavailable right now. Try again shortly.", intent)

        # If the agent produced no answer or the gate rejected it, fall back to the safe reply.
        answer = (result.answer or "").strip()
        if not answer or result.decision.value != "auto_accept":
            answer = _NO_DATA_REPLY

        sources = _format_sources(result, passages)
        return await self._record_and_return(
            chat, tenant, conversation_id, user_id, agent_id, question, answer, intent,
            sources=sources, passages_used=len(passages))

    async def _record_and_return(
        self, chat: ChatService | None, tenant: str, conversation_id: str,
        user_id: str, agent_id: str, question: str, reply: str, intent: str,
        *, sources: list[str] | None = None, passages_used: int = 0,
    ) -> dict:
        if chat is not None:
            if agent_id:
                await chat.store.ensure(
                    tenant, conversation_id, user_id=user_id, agent_id=agent_id,
                    crm_eligible=False)
            await chat.post(tenant, conversation_id, "user", question)
            await chat.post(tenant, conversation_id, "assistant", reply)

        return {
            "reply": reply,
            "intent": intent,
            "conversation_id": conversation_id,
            "sources": sources or [],
            "passages_used": passages_used,
        }
