"""Chat: conversation history + agentic answering. History lives behind an async ChatStore so it
is in-memory in dev/tests and Postgres-backed in prod (same protocol). Voice reuses the same flow."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol

from app.modules.workers.worker import Worker

HISTORY_WINDOW = 20


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
    created_at: object = None


class ChatStore(Protocol):
    async def ensure(self, tenant: str, conversation_id: str, *, user_id: str = "", agent_id: str = "") -> None: ...
    async def append(self, tenant: str, conversation_id: str, role: str, text: str) -> Message: ...
    async def history(self, tenant: str, conversation_id: str, *, limit: int = HISTORY_WINDOW) -> list[Message]: ...
    async def clear(self, tenant: str, conversation_id: str) -> None: ...
    async def list_for_agent(self, tenant: str, agent_id: str) -> list[ConversationSummary]: ...


@dataclass
class InMemoryChatStore:
    _history: dict[tuple[str, str], list[Message]] = field(default_factory=dict)
    _conversations: dict[str, ConversationSummary] = field(default_factory=dict)

    async def ensure(self, tenant: str, conversation_id: str, *, user_id: str = "", agent_id: str = "") -> None:
        self._history.setdefault((tenant, conversation_id), [])
        self._conversations.setdefault(f"{tenant}:{conversation_id}",
                                       ConversationSummary(id=conversation_id, user_id=user_id or "public",
                                                          agent_id=agent_id or "public"))

    async def append(self, tenant: str, conversation_id: str, role: str, text: str) -> Message:
        msg = Message(role=role, text=text)
        self._history.setdefault((tenant, conversation_id), []).append(msg)
        return msg

    async def history(self, tenant: str, conversation_id: str, *, limit: int = HISTORY_WINDOW) -> list[Message]:
        msgs = self._history.get((tenant, conversation_id), [])
        return msgs[-limit:] if limit else list(msgs)

    async def clear(self, tenant: str, conversation_id: str) -> None:
        self._history.pop((tenant, conversation_id), None)

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

    async def find_or_create(self, tenant: str, user_id: str, agent_id: str) -> str:
        """Deterministic private conversation id for a (tenant, user, agent) triple."""
        cid = hashlib.sha1(f"{tenant}:{user_id}:{agent_id}".encode()).hexdigest()[:16]
        await self.store.ensure(tenant, cid, user_id=user_id, agent_id=agent_id)
        return cid

    async def history(self, tenant: str, conversation_id: str, *, limit: int = HISTORY_WINDOW) -> list[Message]:
        return await self.store.history(tenant, conversation_id, limit=limit)

    async def clear(self, tenant: str, conversation_id: str) -> None:
        await self.store.clear(tenant, conversation_id)

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[ConversationSummary]:
        return await self.store.list_for_agent(tenant, agent_id)

    async def post(self, tenant: str, conversation_id: str, role: str, text: str) -> Message:
        return await self.store.append(tenant, conversation_id, role, text)

    async def ask(self, worker: Worker, conversation_id: str, question: str, *, topic: str | None = None) -> Message:
        """Record the user turn, answer via the worker (agentcore), record and return the reply."""
        tenant = worker.config.tenant
        await self.post(tenant, conversation_id, "user", question)
        result = await worker.answer(conversation_id, question, topic=topic)
        return await self.post(tenant, conversation_id, "assistant", result.answer)
