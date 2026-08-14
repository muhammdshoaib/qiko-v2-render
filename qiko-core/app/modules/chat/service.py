"""Chat: conversation history + agentic answering. History lives behind an async ChatStore so it
is in-memory in dev/tests and Postgres-backed in prod (same protocol). Voice reuses the same flow."""
from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.modules.workers.worker import Worker

HISTORY_WINDOW = 20
WorkerRecheck = Callable[[], Awaitable[None]]


class ConversationScopeError(Exception):
    pass


@dataclass
class Message:
    role: str  # user | assistant
    text: str
    created_at: object = None  # datetime | None -- SQL-backed stores populate this; in-memory doesn't need to


@dataclass
class ConversationSummary:
    id: str
    user_id: str
    agent_id: str
    crm_eligible: bool = False
    created_at: object = None


class ChatStore(Protocol):
    async def ensure(
        self, tenant: str, conversation_id: str, *, user_id: str = "", agent_id: str = "",
        crm_eligible: bool = False,
    ) -> None: ...
    async def ensure_for_enabled_agent(
        self, tenant: str, conversation_id: str, *, user_id: str, agent_id: str,
        crm_eligible: bool = False, recheck_worker: WorkerRecheck,
    ) -> None: ...
    async def append(self, tenant: str, conversation_id: str, role: str, text: str) -> Message: ...
    async def append_exchange_for_enabled_agent(
        self, tenant: str, conversation_id: str, *, user_id: str, agent_id: str,
        crm_eligible: bool = False, user_text: str, assistant_text: str,
        recheck_worker: WorkerRecheck,
    ) -> Message: ...
    async def history(self, tenant: str, conversation_id: str, *, limit: int = HISTORY_WINDOW) -> list[Message]: ...
    async def clear(self, tenant: str, conversation_id: str) -> int: ...
    async def list_for_agent(self, tenant: str, agent_id: str) -> list[ConversationSummary]: ...


@dataclass
class InMemoryChatStore:
    _history: dict[tuple[str, str], list[Message]] = field(default_factory=dict)
    _conversations: dict[str, ConversationSummary] = field(default_factory=dict)

    async def ensure(
        self, tenant: str, conversation_id: str, *, user_id: str = "", agent_id: str = "",
        crm_eligible: bool = False,
    ) -> None:
        self._history.setdefault((tenant, conversation_id), [])
        self._conversations.setdefault(
            f"{tenant}:{conversation_id}",
            ConversationSummary(
                id=conversation_id, user_id=user_id or "public",
                agent_id=agent_id or "public", crm_eligible=crm_eligible),
        )

    async def ensure_for_enabled_agent(
        self, tenant: str, conversation_id: str, *, user_id: str, agent_id: str,
        crm_eligible: bool = False, recheck_worker: WorkerRecheck,
    ) -> None:
        await recheck_worker()
        key = f"{tenant}:{conversation_id}"
        current = self._conversations.get(key)
        if current is not None and current.agent_id != agent_id:
            raise ConversationScopeError
        if current is None:
            self._history.setdefault((tenant, conversation_id), [])
            self._conversations[key] = ConversationSummary(
                id=conversation_id, user_id=user_id or "public",
                agent_id=agent_id, crm_eligible=crm_eligible)

    async def append(self, tenant: str, conversation_id: str, role: str, text: str) -> Message:
        msg = Message(role=role, text=text)
        self._history.setdefault((tenant, conversation_id), []).append(msg)
        return msg

    async def append_exchange_for_enabled_agent(
        self, tenant: str, conversation_id: str, *, user_id: str, agent_id: str,
        crm_eligible: bool = False, user_text: str, assistant_text: str,
        recheck_worker: WorkerRecheck,
    ) -> Message:
        await self.ensure_for_enabled_agent(
            tenant, conversation_id, user_id=user_id, agent_id=agent_id,
            crm_eligible=crm_eligible, recheck_worker=recheck_worker)
        await recheck_worker()
        messages = self._history.setdefault((tenant, conversation_id), [])
        messages.extend([
            Message(role="user", text=user_text),
            Message(role="assistant", text=assistant_text),
        ])
        return messages[-1]

    async def history(self, tenant: str, conversation_id: str, *, limit: int = HISTORY_WINDOW) -> list[Message]:
        msgs = self._history.get((tenant, conversation_id), [])
        return msgs[-limit:] if limit else list(msgs)

    async def clear(self, tenant: str, conversation_id: str) -> int:
        return len(self._history.pop((tenant, conversation_id), []) or [])

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[ConversationSummary]:
        prefix = f"{tenant}:"
        return [c for key, c in self._conversations.items()
               if key.startswith(prefix) and c.agent_id == agent_id]


@dataclass
class ChatService:
    store: ChatStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryChatStore()

    async def find_or_create(self, tenant: str, user_id: str, agent_id: str,
                             recheck_worker: WorkerRecheck | None = None) -> str:
        """Deterministic private conversation id for a (tenant, user, agent) triple."""
        cid = hashlib.sha1(f"{tenant}:{user_id}:{agent_id}".encode()).hexdigest()[:16]
        if recheck_worker is None:
            await self.store.ensure(
                tenant, cid, user_id=user_id, agent_id=agent_id, crm_eligible=True)
        else:
            await self.store.ensure_for_enabled_agent(
                tenant, cid, user_id=user_id, agent_id=agent_id, crm_eligible=True,
                recheck_worker=recheck_worker)
        return cid

    async def history(self, tenant: str, conversation_id: str, *, limit: int = HISTORY_WINDOW) -> list[Message]:
        return await self.store.history(tenant, conversation_id, limit=limit)

    async def clear(self, tenant: str, conversation_id: str) -> int:
        """Returns how many messages were removed, for the audit row."""
        return await self.store.clear(tenant, conversation_id)

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[ConversationSummary]:
        return await self.store.list_for_agent(tenant, agent_id)

    async def post(self, tenant: str, conversation_id: str, role: str, text: str) -> Message:
        return await self.store.append(tenant, conversation_id, role, text)

    async def ask(self, worker: Worker, conversation_id: str, question: str, *, topic: str | None = None,
                  agent_id: str | None = None,
                  recheck_worker: WorkerRecheck | None = None,
                  additional_context: list[str] | None = None) -> Message:
        """Record the user turn, answer via the worker (agentcore), record and return the reply.

        `agent_id` (the real agent id, not worker.name -- see public.py's public_ask for why
        that distinction matters) is used to explicitly create the conversation up front if it
        doesn't exist yet, so a caller that never calls /chat/conversations first (e.g. the
        dashboard's own test-chat, which mints its own client-side conversation id) still gets
        scoped to the right agent. A conversation created here is not CRM-eligible. An existing
        public or explicitly created conversation keeps its original eligibility."""
        tenant = worker.config.tenant
        result = await worker.answer(
            conversation_id, question, topic=topic,
            additional_context=additional_context,
            recheck_worker=recheck_worker)
        if agent_id and recheck_worker is not None:
            return await self.store.append_exchange_for_enabled_agent(
                tenant, conversation_id, user_id="public", agent_id=agent_id,
                crm_eligible=False, user_text=question, assistant_text=result.answer,
                recheck_worker=recheck_worker)
        if agent_id:
            await self.store.ensure(
                tenant, conversation_id, user_id="public", agent_id=agent_id,
                crm_eligible=False)
        await self.post(tenant, conversation_id, "user", question)
        return await self.post(tenant, conversation_id, "assistant", result.answer)
