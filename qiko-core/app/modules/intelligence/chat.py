"""Intelligence Worker chat: answer questions grounded in captured signals.

Follows the pattern in app.modules.finance.chat but sits on top of the shared Worker
(agentcore + knowledge) so grounding, citations, cost caps and the flywheel all come for free.
"""
from __future__ import annotations

import uuid

from app.modules.agentcore.models import AgentResult
from app.modules.chat.service import ChatService
from app.modules.workers.worker import StubProviderUnavailable, Worker

_GREETINGS = ("hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings")
_CAPABILITY = ("what can you do", "help", "capabilities", "what do you do", "how can you help")

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
    return "data"


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
