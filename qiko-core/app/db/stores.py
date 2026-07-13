"""Async DB-backed stores (SQLAlchemy 2.0 async). Drop-in replacements for the in-memory stores:
they return the same domain dataclasses, so callers depend only on the store protocols.

These persist across restarts (single-session revocation and the feedback flywheel survive a
redeploy), which the in-memory stubs did not.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Agent as AgentRow
from app.db.models import Assignment as AssignmentRow
from app.db.models import Contact as ContactRow
from app.db.models import Conversation as ConversationRow
from app.db.models import CrmAction as CrmActionRow
from app.db.models import Lead as LeadRow
from app.db.models import Message as MessageRow
from app.db.models import PackAnswer as PackAnswerRow
from app.db.models import PackRequirement as PackRequirementRow
from app.db.models import Passage as PassageRow
from app.db.models import PlatformAdmin as PlatformAdminRow
from app.db.models import RfpPack as RfpPackRow
from app.db.models import Team as TeamRow
from app.db.models import TeamMember as TeamMemberRow
from app.db.models import Tenant as TenantRow
from app.db.models import TeamsWebhook as TeamsWebhookRow
from app.db.models import User as UserRow
from app.db.models import VerifiedAnswer
from app.modules.agents.service import Agent
from app.modules.assignments.service import Assignment, AssignmentNotFound
from app.modules.channels.teams_integration import TeamsIntegration
from app.modules.chat.service import ConversationSummary, Message
from app.modules.crm.service import Contact, CrmAction
from app.modules.identity.admin_rbac import AdminRole
from app.modules.identity.rbac import Role
from app.modules.identity.store import User
from app.modules.knowledge.models import Passage
from app.modules.leads.service import Lead
from app.modules.rfp.service import CachedAnswer, PackRequirement, RfpPack, RfpPackNotFound
from app.modules.teams.service import Team


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
                     status=r.status, config=dict(r.config or {}), created_at=r.created_at)

    async def add(self, agent: Agent) -> Agent:
        async with self.sessionmaker() as s, s.begin():
            s.add(AgentRow(id=agent.id, tenant_id=agent.tenant, name=agent.name,
                           atype=agent.atype, status=agent.status, config=agent.config,
                           created_at=agent.created_at))
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

    async def update_config(self, tenant: str, agent_id: str, patch: dict) -> Agent:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(AgentRow, agent_id)
            if row is None or row.tenant_id != tenant:
                raise KeyError(agent_id)
            row.config = {**(row.config or {}), **patch}
            return self._to_domain(row)


@dataclass
class SqlRfpPackStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: RfpPackRow) -> RfpPack:
        return RfpPack(id=r.id, tenant=r.tenant_id, agent_id=r.agent_id, title=r.title,
                       client_name=r.client_name, deadline=r.deadline, stage=r.stage,
                       created_at=r.created_at, document_text=r.document_text or "",
                       outcome=r.outcome, outcome_reason=r.outcome_reason or "",
                       outcome_value=r.outcome_value, outcome_at=r.outcome_at)

    async def add(self, pack: RfpPack) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            s.add(RfpPackRow(id=pack.id, tenant_id=pack.tenant, agent_id=pack.agent_id,
                             title=pack.title, client_name=pack.client_name,
                             deadline=pack.deadline, stage=pack.stage,
                             document_text=pack.document_text))
        return pack

    async def list(self, tenant: str, *, agent_id: str | None = None) -> list[RfpPack]:
        async with self.sessionmaker() as s:
            q = select(RfpPackRow).where(RfpPackRow.tenant_id == tenant)
            if agent_id is not None:
                q = q.where(RfpPackRow.agent_id == agent_id)
            rows = (await s.execute(q)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def get(self, tenant: str, pack_id: str) -> RfpPack | None:
        async with self.sessionmaker() as s:
            row = await s.get(RfpPackRow, pack_id)
            if row is None or row.tenant_id != tenant:
                return None
            return self._to_domain(row)

    async def set_stage(self, tenant: str, pack_id: str, stage: str) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(RfpPackRow, pack_id)
            if row is None or row.tenant_id != tenant:
                raise RfpPackNotFound(pack_id)
            row.stage = stage
            return self._to_domain(row)

    async def set_document_text(self, tenant: str, pack_id: str, text: str) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(RfpPackRow, pack_id)
            if row is None or row.tenant_id != tenant:
                raise RfpPackNotFound(pack_id)
            row.document_text = text
            return self._to_domain(row)

    async def set_outcome(self, tenant: str, pack_id: str, *, outcome: str | None,
                          reason: str, value: float | None) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(RfpPackRow, pack_id)
            if row is None or row.tenant_id != tenant:
                raise RfpPackNotFound(pack_id)
            row.outcome, row.outcome_reason, row.outcome_value = outcome, reason, value
            row.outcome_at = datetime.now(timezone.utc) if outcome else None
            return self._to_domain(row)

    async def delete(self, tenant: str, pack_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(RfpPackRow, pack_id)
            if row is not None and row.tenant_id == tenant:
                await s.delete(row)


@dataclass
class SqlRequirementStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: PackRequirementRow) -> PackRequirement:
        return PackRequirement(id=r.id, tenant=r.tenant_id, pack_id=r.pack_id, req_id=r.req_id,
                               title=r.title, classification=r.classification, requirement=r.requirement)

    async def replace_all(self, tenant: str, pack_id: str, items: list[PackRequirement]) -> list[PackRequirement]:
        async with self.sessionmaker() as s, s.begin():
            await s.execute(delete(PackRequirementRow).where(
                PackRequirementRow.tenant_id == tenant, PackRequirementRow.pack_id == pack_id))
            for item in items:
                s.add(PackRequirementRow(id=item.id, tenant_id=tenant, pack_id=pack_id, req_id=item.req_id,
                                         title=item.title, classification=item.classification,
                                         requirement=item.requirement))
        return items

    async def list(self, tenant: str, pack_id: str) -> list[PackRequirement]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(PackRequirementRow).where(
                PackRequirementRow.tenant_id == tenant, PackRequirementRow.pack_id == pack_id))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            await s.execute(delete(PackRequirementRow).where(
                PackRequirementRow.tenant_id == tenant, PackRequirementRow.pack_id == pack_id))


@dataclass
class SqlPackAnswerStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: PackAnswerRow) -> CachedAnswer:
        return CachedAnswer(pack_id=r.pack_id, req_id=r.req_id, tenant=r.tenant_id, answer=r.answer,
                            confidence=r.confidence, decision=r.decision, citations=r.citations, note=r.note)

    async def get_all(self, tenant: str, pack_id: str) -> dict[str, CachedAnswer]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(PackAnswerRow).where(
                PackAnswerRow.tenant_id == tenant, PackAnswerRow.pack_id == pack_id))).scalars().all()
            return {r.req_id: self._to_domain(r) for r in rows}

    async def put(self, tenant: str, pack_id: str, req_id: str, answer: CachedAnswer) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PackAnswerRow, (pack_id, req_id))
            if row is None:
                s.add(PackAnswerRow(pack_id=pack_id, req_id=req_id, tenant_id=tenant, answer=answer.answer,
                                    confidence=answer.confidence, decision=answer.decision,
                                    citations=answer.citations, note=answer.note))
            elif row.tenant_id == tenant:
                row.answer, row.confidence = answer.answer, answer.confidence
                row.decision, row.citations, row.note = answer.decision, answer.citations, answer.note

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            await s.execute(delete(PackAnswerRow).where(
                PackAnswerRow.tenant_id == tenant, PackAnswerRow.pack_id == pack_id))


@dataclass
class SqlAssignmentStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: AssignmentRow) -> Assignment:
        return Assignment(id=r.id, tenant=r.tenant_id, pack_id=r.pack_id, agent_id=r.agent_id,
                          rfp_title=r.rfp_title, section_id=r.section_id, section_title=r.section_title,
                          assignee_user_id=r.assignee_user_id, assigned_by_user_id=r.assigned_by_user_id,
                          question=r.question, status=r.status, due_at=r.due_at,
                          completed_at=r.completed_at, created_at=r.created_at)

    async def add(self, a: Assignment) -> Assignment:
        async with self.sessionmaker() as s, s.begin():
            s.add(AssignmentRow(id=a.id, tenant_id=a.tenant, pack_id=a.pack_id, agent_id=a.agent_id,
                                rfp_title=a.rfp_title, section_id=a.section_id, section_title=a.section_title,
                                assignee_user_id=a.assignee_user_id, assigned_by_user_id=a.assigned_by_user_id,
                                question=a.question, status=a.status, due_at=a.due_at))
        return a

    async def list(self, tenant: str, *, pack_id: str | None = None,
                   assignee_user_id: str | None = None, status: str | None = None) -> list[Assignment]:
        async with self.sessionmaker() as s:
            q = select(AssignmentRow).where(AssignmentRow.tenant_id == tenant)
            if pack_id is not None:
                q = q.where(AssignmentRow.pack_id == pack_id)
            if assignee_user_id is not None:
                q = q.where(AssignmentRow.assignee_user_id == assignee_user_id)
            if status is not None:
                q = q.where(AssignmentRow.status == status)
            rows = (await s.execute(q)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def get(self, tenant: str, assignment_id: str) -> Assignment | None:
        async with self.sessionmaker() as s:
            row = await s.get(AssignmentRow, assignment_id)
            if row is None or row.tenant_id != tenant:
                return None
            return self._to_domain(row)

    async def update(self, tenant: str, assignment_id: str, **fields) -> Assignment:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(AssignmentRow, assignment_id)
            if row is None or row.tenant_id != tenant:
                raise AssignmentNotFound(assignment_id)
            for k, v in fields.items():
                setattr(row, k, v)
            return self._to_domain(row)

    async def delete_by_section(self, tenant: str, pack_id: str, section_id: str) -> int:
        async with self.sessionmaker() as s, s.begin():
            result = await s.execute(delete(AssignmentRow).where(
                AssignmentRow.tenant_id == tenant, AssignmentRow.pack_id == pack_id,
                AssignmentRow.section_id == section_id))
            return result.rowcount or 0

    async def delete_by_pack(self, tenant: str, pack_id: str) -> int:
        async with self.sessionmaker() as s, s.begin():
            result = await s.execute(delete(AssignmentRow).where(
                AssignmentRow.tenant_id == tenant, AssignmentRow.pack_id == pack_id))
            return result.rowcount or 0


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
            msgs = [Message(role=r.role, text=r.body, created_at=r.created_at) for r in rows]
            return msgs[-limit:] if limit else msgs

    async def clear(self, tenant: str, conversation_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            await s.execute(delete(MessageRow).where(MessageRow.tenant_id == tenant,
                                                     MessageRow.conversation_id == conversation_id))

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[ConversationSummary]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(ConversationRow).where(ConversationRow.tenant_id == tenant,
                                              ConversationRow.agent_id == agent_id)
                .order_by(ConversationRow.created_at))).scalars().all()
            return [ConversationSummary(id=r.id, user_id=r.user_id, agent_id=r.agent_id, created_at=r.created_at)
                   for r in rows]


@dataclass
class SqlAdminOrgStore:
    """Persists the platform-admin registry (SCRUM-80) -- previously in-memory, wiped on every
    redeploy, which made /admin/org/bootstrap a "first caller after a redeploy wins" race."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def get(self, email: str) -> AdminRole | None:
        async with self.sessionmaker() as s:
            row = await s.get(PlatformAdminRow, email.lower())
            return AdminRole(row.role) if row else None

    async def set(self, email: str, role: AdminRole) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PlatformAdminRow, email.lower())
            if row is None:
                s.add(PlatformAdminRow(email=email.lower(), role=role.value))
            else:
                row.role = role.value

    async def delete(self, email: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PlatformAdminRow, email.lower())
            if row is not None:
                await s.delete(row)

    async def is_empty(self) -> bool:
        async with self.sessionmaker() as s:
            row = (await s.execute(select(PlatformAdminRow).limit(1))).scalars().first()
            return row is None


@dataclass
class SqlLeadStore:
    """Persists captured leads (enterprise/RAG-wired forms) -- previously in-memory only, so every
    lead was lost on the next redeploy."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, lead: Lead) -> Lead:
        async with self.sessionmaker() as s, s.begin():
            s.add(LeadRow(id=lead.id, tenant_id=lead.tenant, kind=lead.kind, name=lead.name,
                          email=lead.email, payload=lead.payload))
        return lead

    async def list(self, tenant: str) -> list[Lead]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(LeadRow).where(LeadRow.tenant_id == tenant).order_by(LeadRow.created_at))).scalars().all()
            return [Lead(id=r.id, tenant=r.tenant_id, kind=r.kind, name=r.name, email=r.email,
                        payload=r.payload or {}, created_at=r.created_at) for r in rows]


@dataclass
class SqlTeamStore:
    """Persists teams + membership -- previously in-memory only, so every team lost all but its
    owner (recreated at signup) on the next redeploy."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def _load(self, s: AsyncSession, team_id: str) -> Team | None:
        team_row = await s.get(TeamRow, team_id)
        if team_row is None:
            return None
        member_rows = (await s.execute(
            select(TeamMemberRow).where(TeamMemberRow.team_id == team_id))).scalars().all()
        return Team(id=team_row.id, tenant=team_row.tenant_id,
                    members={m.user_id: Role(m.role) for m in member_rows})

    async def add(self, team: Team) -> Team:
        async with self.sessionmaker() as s, s.begin():
            s.add(TeamRow(id=team.id, tenant_id=team.tenant))
            for user_id, role in team.members.items():
                s.add(TeamMemberRow(team_id=team.id, user_id=user_id, role=role.value))
        return team

    async def get(self, team_id: str) -> Team | None:
        async with self.sessionmaker() as s:
            return await self._load(s, team_id)

    async def set_member(self, team_id: str, user_id: str, role: Role) -> Team:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(TeamMemberRow, (team_id, user_id))
            if row is None:
                s.add(TeamMemberRow(team_id=team_id, user_id=user_id, role=role.value))
            else:
                row.role = role.value
        async with self.sessionmaker() as s:
            return await self._load(s, team_id)

    async def remove_member(self, team_id: str, user_id: str) -> Team:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(TeamMemberRow, (team_id, user_id))
            if row is not None:
                await s.delete(row)
        async with self.sessionmaker() as s:
            return await self._load(s, team_id)


@dataclass
class SqlTeamsIntegrationStore:
    """Persists each tenant's Microsoft Teams Incoming Webhook -- previously would have had no
    persistence at all (a fresh in-memory dict), so the connection was lost on every redeploy."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def get(self, tenant: str) -> TeamsIntegration | None:
        async with self.sessionmaker() as s:
            row = await s.get(TeamsWebhookRow, tenant)
            if row is None:
                return None
            return TeamsIntegration(tenant=tenant, enc_webhook_url=row.enc_webhook_url,
                                    connected_at=row.connected_at)

    async def set(self, tenant: str, webhook_url: str) -> TeamsIntegration:
        from app.core.crypto import encrypt

        enc = encrypt(webhook_url)
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(TeamsWebhookRow, tenant)
            if row is None:
                row = TeamsWebhookRow(tenant_id=tenant, enc_webhook_url=enc)
                s.add(row)
            else:
                row.enc_webhook_url = enc
        return TeamsIntegration(tenant=tenant, enc_webhook_url=enc)

    async def delete(self, tenant: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(TeamsWebhookRow, tenant)
            if row is not None:
                await s.delete(row)


def _contact_from_row(r: ContactRow) -> Contact:
    return Contact(id=r.id, tenant=r.tenant_id, agent_id=r.agent_id, conversation_id=r.conversation_id,
                   name=r.name, email=r.email, phone=r.phone, status=r.status,
                   estimated_value=r.estimated_value, currency=r.currency, ai_summary=r.ai_summary,
                   sentiment=r.sentiment, key_topics=list(r.key_topics or []),
                   created_at=r.created_at, updated_at=r.updated_at)


@dataclass
class SqlContactStore:
    """Persists CRM/Sales Pipeline contacts -- real data derived from a worker's own chat
    history, replacing what was a client-side-only mock in the earlier qiko-frontend build."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def get(self, tenant: str, contact_id: str) -> Contact | None:
        async with self.sessionmaker() as s:
            row = await s.get(ContactRow, contact_id)
            return _contact_from_row(row) if row and row.tenant_id == tenant else None

    async def get_by_conversation(self, tenant: str, agent_id: str, conversation_id: str) -> Contact | None:
        async with self.sessionmaker() as s:
            row = (await s.execute(
                select(ContactRow).where(ContactRow.tenant_id == tenant, ContactRow.agent_id == agent_id,
                                         ContactRow.conversation_id == conversation_id))).scalars().first()
            return _contact_from_row(row) if row else None

    async def add(self, contact: Contact) -> Contact:
        async with self.sessionmaker() as s, s.begin():
            s.add(ContactRow(id=contact.id, tenant_id=contact.tenant, agent_id=contact.agent_id,
                             conversation_id=contact.conversation_id, name=contact.name, email=contact.email,
                             phone=contact.phone, status=contact.status, estimated_value=contact.estimated_value,
                             currency=contact.currency, ai_summary=contact.ai_summary, sentiment=contact.sentiment,
                             key_topics=contact.key_topics, created_at=contact.created_at,
                             updated_at=contact.updated_at))
        return contact

    async def update(self, contact: Contact) -> Contact:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(ContactRow, contact.id)
            if row is not None:
                row.name, row.email, row.phone = contact.name, contact.email, contact.phone
                row.status, row.estimated_value = contact.status, contact.estimated_value
                row.ai_summary, row.sentiment = contact.ai_summary, contact.sentiment
                row.key_topics, row.updated_at = contact.key_topics, contact.updated_at
        return contact

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[Contact]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(ContactRow).where(ContactRow.tenant_id == tenant,
                                         ContactRow.agent_id == agent_id))).scalars().all()
            return [_contact_from_row(r) for r in rows]


@dataclass
class SqlActionStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, action: CrmAction) -> CrmAction:
        async with self.sessionmaker() as s, s.begin():
            s.add(CrmActionRow(id=action.id, tenant_id=action.tenant, contact_id=action.contact_id,
                               action_type=action.action_type, title=action.title,
                               description=action.description, priority=action.priority,
                               status=action.status, created_at=action.created_at))
        return action

    async def list_for_contact(self, tenant: str, contact_id: str) -> list[CrmAction]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(CrmActionRow).where(CrmActionRow.tenant_id == tenant,
                                           CrmActionRow.contact_id == contact_id))).scalars().all()
            return [CrmAction(id=r.id, tenant=r.tenant_id, contact_id=r.contact_id, title=r.title,
                              action_type=r.action_type, description=r.description or "",
                              priority=r.priority, status=r.status, created_at=r.created_at) for r in rows]

    async def update_status(self, tenant: str, action_id: str, status: str) -> CrmAction | None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(CrmActionRow, action_id)
            if row is None or row.tenant_id != tenant:
                return None
            row.status = status
            return CrmAction(id=row.id, tenant=row.tenant_id, contact_id=row.contact_id, title=row.title,
                             action_type=row.action_type, description=row.description or "",
                             priority=row.priority, status=row.status, created_at=row.created_at)
