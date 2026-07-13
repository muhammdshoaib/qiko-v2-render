"""Public/embed chat + Studio enrichment.

Public chat is only served for a worker whose agent is 'ready'. Studio users can enrich the
grounded context with blocks from an external data agent. Answering stays agentic-first: it goes
through the worker -> agentcore (generator/critic/gate), never a direct LLM call.
"""
from __future__ import annotations

from app.modules.agentcore.models import Requirement
from app.modules.chat.service import ChatService, Message
from app.modules.workers.worker import Worker


class AgentNotReadyError(Exception):
    pass


def studio_context_blocks(studio: dict | None) -> list[str]:
    """Flatten the external Studio payload (fileList/schema/summary/...) into context strings."""
    if not studio:
        return []
    blocks: list[str] = []
    for key in ("summary", "schema", "fileList", "userNamespaces"):
        val = studio.get(key)
        if isinstance(val, (list, tuple)):
            blocks.extend(str(v) for v in val if v)
        elif val:
            blocks.append(str(val))
    return blocks


async def public_ask(worker: Worker, chat: ChatService, *, agent_id: str, user_email: str, question: str,
                     agent_ready: bool, topic: str | None = None, studio: dict | None = None) -> Message:
    """Answer a public/embed chat turn. Requires the agent to be ready; merges Studio context
    into the grounded requirement before running agentcore.

    `agent_id` is the real agent id (as used everywhere else a worker is referenced, e.g. the
    CRM pipeline / Sections tab URLs) -- NOT worker.name (its display name, which is what this
    used to key the conversation by, so every public-embed chat silently recorded itself under
    the wrong agent and could never be found by anything looking up "this worker's contacts")."""
    if not agent_ready:
        raise AgentNotReadyError("agent is not ready for public chat")
    tenant = worker.config.tenant
    cid = await chat.find_or_create(tenant, user_email, agent_id)
    await chat.post(tenant, cid, "user", question)

    extra = studio_context_blocks(studio)
    passages = await worker.knowledge.retrieve(tenant, question, k=worker.config.retrieval_k)
    context = [p.text for p in passages] + extra
    req = Requirement(id=cid, text=question, context=context, topic=topic)
    result = await worker.agent.run(req, tenant=tenant)
    return await chat.post(tenant, cid, "assistant", result.answer)
