"""Async DB-backed stores (SQLAlchemy 2.0 async). Drop-in replacements for the in-memory stores:
they return the same domain dataclasses, so callers depend only on the store protocols.

These persist across restarts (single-session revocation and the feedback flywheel survive a
redeploy), which the in-memory stubs did not.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Agent as AgentRow
from app.db.models import Conversation as ConversationRow
from app.db.models import Message as MessageRow
from app.db.models import Passage as PassageRow
from app.db.models import Tenant as TenantRow
from app.db.models import User as UserRow
from app.db.models import VerifiedAnswer
from app.modules.agents.service import Agent
from app.modules.chat.service import Message
from app.modules.identity.rbac import Role
from app.modules.identity.store import User
from app.modules.knowledge.models import Passage


@dataclass
class SqlUserStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, user: User) -> User:
        async with self.sessionmaker() as s, s.begin():
            # Signup creates brand-new tenants on the fly; ensure the FK target exists first
            # (idempotent -- a no-op for tenants that are already there). Dialect-agnostic
            # check-then-insert so this works on both Postgres (prod) and SQLite (tests).
            if await s.get(TenantRow, user.tenant) is None:
                s.add(TenantRow(id=user.tenant, name=user.tenant))
            s.add(UserRow(id=user.id, email=user.email.lower(), password_hash=user.password_hash,
                          tenant_id=user.tenant, role=user.role.value, twofa_enabled=user.twofa_enabled,
                          totp_secret=user.totp_secret, current_sid=user.current_sid))
        return user

    async def _to_domain(self, row: UserRow | None) -> User | None:
        if row is None:
            return None
        return User(id=row.id, email=row.email, password_hash=row.password_hash, tenant=row.tenant_id,
                    role=Role(row.role), twofa_enabled=row.twofa_enabled, totp_secret=row.totp_secret,
                    current_sid=row.current_sid)

    async def get_by_email(self, email: str) -> User | None:
        async with self.sessionmaker() as s:
            row = (await s.execute(select(UserRow).where(UserRow.email == email.lower()))).scalar_one_or_none()
            return await self._to_domain(row)

    async def get_by_id(self, user_id: str) -> User | None:
        async with self.sessionmaker() as s:
            return await self._to_domain(await s.get(UserRow, user_id))

    async def set_sid(self, user_id: str, sid: str | None) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                row.current_sid = sid

    async def enable_twofa(self, user_id: str, secret: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                row.twofa_enabled = True
                row.totp_secret = secret

    async def set_password(self, user_id: str, password_hash: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                row.password_hash = password_hash


@dataclass
class SqlVerifiedStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, tenant: str, topic: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if text in await self.get(tenant, topic):  # dedupe
            return
        async with self.sessionmaker() as s, s.begin():
            s.add(VerifiedAnswer(tenant_id=tenant, topic=topic, body=text))

    async def get(self, tenant: str, topic: str) -> list[str]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(VerifiedAnswer.body)
                .where(VerifiedAnswer.tenant_id == tenant, VerifiedAnswer.topic == topic)
                .order_by(VerifiedAnswer.id))).scalars().all()
            return list(rows)


@dataclass
class SqlVectorStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, passage: Passage) -> None:
        async with self.sessionmaker() as s, s.begin():
            s.add(PassageRow(id=passage.id, tenant_id=passage.tenant, doc_id=passage.doc_id,
                             text=passage.text, embedding=passage.embedding))

    async def get(self, tenant: str) -> list[Passage]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(PassageRow).where(PassageRow.tenant_id == tenant))).scalars().all()
            return [Passage(id=r.id, tenant=r.tenant_id, doc_id=r.doc_id, text=r.text,
                            embedding=list(r.embedding or [])) for r in rows]

    async def delete_doc(self, tenant: str, doc_id: str) -> int:
        async with self.sessionmaker() as s, s.begin():
            result = await s.execute(
                delete(PassageRow).where(PassageRow.tenant_id == tenant, PassageRow.doc_id == doc_id))
            return result.rowcount or 0


@dataclass
class SqlAgentStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: AgentRow) -> Agent:
        return Agent(id=r.id, tenant=r.tenant_id, name=r.name, atype=r.atype,
                     status=r.status, config=dict(r.config or {}))

    async def add(self, agent: Agent) -> Agent:
        async with self.sessionmaker() as s, s.begin():
            s.add(AgentRow(id=agent.id, tenant_id=agent.tenant, name=agent.name,
                           atype=agent.atype, status=agent.status, config=agent.config))
        return agent

    async def list(self, tenant: str) -> list[Agent]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(AgentRow).where(AgentRow.tenant_id == tenant))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def count(self, tenant: str) -> int:
        return len(await self.list(tenant))

    async def get(self, tenant: str, agent_id: str) -> Agent | None:
        async with self.sessionmaker() as s:
            row = await s.get(AgentRow, agent_id)
            if row is None or row.tenant_id != tenant:
                return None
            return self._to_domain(row)

    async def mark_ready(self, tenant: str, agent_id: str) -> Agent:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(AgentRow, agent_id)
            if row is None or row.tenant_id != tenant:
                raise KeyError(agent_id)
            row.status = "ready"
            return self._to_domain(row)


@dataclass
class SqlChatStore:
    """Postgres-backed chat history (Conversation/Message tables), tenant-scoped."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def ensure(self, tenant: str, conversation_id: str, *, user_id: str = "", agent_id: str = "") -> None:
        async with self.sessionmaker() as s, s.begin():
            if await s.get(ConversationRow, conversation_id) is None:
                s.add(ConversationRow(id=conversation_id, tenant_id=tenant,
                                      user_id=user_id or "public", agent_id=agent_id or "public"))

    async def append(self, tenant: str, conversation_id: str, role: str, text: str) -> Message:
        await self.ensure(tenant, conversation_id)
        async with self.sessionmaker() as s, s.begin():
            s.add(MessageRow(conversation_id=conversation_id, tenant_id=tenant, role=role, body=text))
        return Message(role=role, text=text)

    async def history(self, tenant: str, conversation_id: str, *, limit: int = 20) -> list[Message]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(MessageRow).where(MessageRow.tenant_id == tenant,
                                         MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.id))).scalars().all()
            msgs = [Message(role=r.role, text=r.body) for r in rows]
            return msgs[-limit:] if limit else msgs

    async def clear(self, tenant: str, conversation_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            await s.execute(delete(MessageRow).where(MessageRow.tenant_id == tenant,
                                                     MessageRow.conversation_id == conversation_id))
