"""Public/embed chat + Studio enrichment.

Public chat is only served for a worker whose agent is 'ready'. Studio users can enrich the
grounded context with blocks from an external data agent. Answering stays agentic-first: it goes
through the worker -> agentcore (generator/critic/gate), never a direct LLM call.
"""
from __future__ import annotations

from app.core.deps import WorkerRecheck
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


async def public_ask(worker: Worker, chat: ChatService, *, agent_id: str,
                     user_email: str, question: str, recheck_worker: WorkerRecheck,
                     topic: str | None = None, studio: dict | None = None) -> Message:
    """Answer a public/embed chat turn. Requires the agent to be ready; merges Studio context
    into the grounded requirement before running agentcore.

    `agent_id` is the real agent id (as used everywhere else a worker is referenced, e.g. the
    CRM pipeline / Sections tab URLs) -- NOT worker.name (its display name, which is what this
    used to key the conversation by, so every public-embed chat silently recorded itself under
    the wrong agent and could never be found by anything looking up "this worker's contacts")."""
    tenant = worker.config.tenant
    await recheck_worker()
    cid = await chat.find_or_create(
        tenant, user_email, agent_id, recheck_worker=recheck_worker)
    return await chat.ask(
        worker, cid, question, topic=topic, agent_id=agent_id,
        recheck_worker=recheck_worker,
        additional_context=studio_context_blocks(studio),
    )
