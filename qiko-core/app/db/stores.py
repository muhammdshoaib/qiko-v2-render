"""Async DB-backed stores (SQLAlchemy 2.0 async). Drop-in replacements for the in-memory stores:
they return the same domain dataclasses, so callers depend only on the store protocols.

These persist across restarts (single-session revocation and the feedback flywheel survive a
redeploy), which the in-memory stubs did not.
"""
from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.crypto import decrypt, encrypt

from app.db.models import Agent as AgentRow
from app.db.models import AgentStateAudit as AgentStateAuditRow
from app.db.models import Assignment as AssignmentRow
from app.db.models import ConsentRecord as ConsentRecordRow
from app.db.models import Contact as ContactRow
from app.db.models import Conversation as ConversationRow
from app.db.models import CrmAction as CrmActionRow
from app.db.models import FinanceChatMessage as FinanceChatMessageRow
from app.db.models import FinanceFile as FinanceFileRow
from app.db.models import Lead as LeadRow
from app.db.models import Message as MessageRow
from app.db.models import MfaBackupCode as MfaBackupCodeRow
from app.db.models import Notification as NotificationRow
from app.db.models import PackAnswer as PackAnswerRow
from app.db.models import PackQuestion as PackQuestionRow
from app.db.models import PackRequirement as PackRequirementRow
from app.db.models import PackSection as PackSectionRow
from app.db.models import Passage as PassageRow
from app.db.models import PasswordResetOtp as PasswordResetOtpRow
from app.db.models import PendingSignup as PendingSignupRow
from app.db.models import PendingTeamInvite as PendingTeamInviteRow
from app.db.models import PlatformAdmin as PlatformAdminRow
from app.db.models import AuditArchiveDigest as AuditArchiveDigestRow
from app.db.models import AuditEventRow
from app.db.models import AiCostCap as AiCostCapRow
from app.db.models import AiUsageEvent as AiUsageEventRow
from app.db.models import PlatformAdminAudit as PlatformAdminAuditRow
from app.db.models import PolicyRelease as PolicyReleaseRow
from app.db.models import RfpPack as RfpPackRow
from app.db.models import SalesIntelActivityLog as SalesIntelActivityLogRow
from app.db.models import SalesIntelIngestionSource as SalesIntelIngestionSourceRow
from app.db.models import SalesIntelOpportunity as SalesIntelOpportunityRow
from app.db.models import SalesIntelIngestFilter as SalesIntelIngestFilterRow
from app.db.models import SalesIntelSalesforceConnection as SalesIntelSalesforceConnectionRow
from app.db.models import Team as TeamRow
from app.db.models import TeamMember as TeamMemberRow
from app.db.models import Tenant as TenantRow
from app.db.models import TeamsWebhook as TeamsWebhookRow
from app.db.models import User as UserRow
from app.db.models import VerifiedAnswer
from app.modules.agents.service import Agent, AgentStateAudit, PlanLimitError
from app.modules.assignments.service import Assignment, AssignmentNotFound
from app.modules.channels.teams_integration import TeamsIntegration
from app.modules.consent.models import ConsentChoices, ConsentRecord, ConsentSource, PolicyRelease
from app.modules.consent.service import (
    active_pseudonym_version,
    derive_action,
    pseudonymous_subject,
    same_consent_decision,
)
from app.core.deps import WorkerUnavailable
from app.modules.chat.service import ConversationScopeError, ConversationSummary, Message
from app.modules.crm.service import Contact, CrmAction
from app.modules.finance.models import FinanceChatMessage, FinanceFile
from app.modules.ai.caps import CostCap
from app.modules.ai.usage import AgentUsageSummary, UsageEvent, UsageTotals, summarise_agents
from app.modules.ai.usage import dimensions as usage_dimensions
from app.modules.ai.usage import group as usage_group
from app.modules.identity.admin_rbac import (
    AdminGrantAudit,
    AdminIdentity,
    AdminRole,
    Capability,
    effective_capabilities,
    read_capabilities,
)
from app.modules.identity.onboarding import hash_otp, new_otp_code
from app.modules.identity.pending_signup import PendingSignup, hash_signup_code
from app.modules.identity import twofa
from app.modules.identity.rbac import Role
from app.modules.identity.security import verify_password
from app.modules.identity.store import User, UserDirectoryEntry
from app.modules.identity.team_access import PendingInvite
from app.modules.knowledge.models import Passage
from app.modules.leads.service import Lead
from app.modules.notifications.models import Notification
from app.modules.rfp.service import CachedAnswer, PackRequirement, RfpPack, RfpPackNotFound
from app.modules.rfp.tree import (
    PackQuestion,
    PackQuestionNotFound,
    PackSection,
    PackSectionNotFound,
)
from app.modules.sales_intelligence.models import (
    ActivityLog,
    IngestFilterSetting,
    IngestionSource,
    Opportunity,
    SalesforceConnection,
    _apply_opportunity_filters,
)
from app.modules.teams.service import Team


def _encrypt_totp(secret: str | None) -> str | None:
    return f"enc:{encrypt(secret)}" if secret else None


def _decrypt_totp(secret: str | None) -> str | None:
    return decrypt(secret[4:]) if secret and secret.startswith("enc:") else secret


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
            s.add(UserRow(id=user.id, email=user.email.lower(), name=user.name,
                          password_hash=user.password_hash,
                          tenant_id=user.tenant, role=user.role.value, twofa_enabled=user.twofa_enabled,
                          totp_secret=_encrypt_totp(user.totp_secret), current_sid=user.current_sid))
        return user

    async def _to_domain(self, row: UserRow | None) -> User | None:
        if row is None:
            return None
        return User(id=row.id, email=row.email, password_hash=row.password_hash, tenant=row.tenant_id,
                    role=Role(row.role), twofa_enabled=row.twofa_enabled,
                    totp_secret=_decrypt_totp(row.totp_secret),
                    current_sid=row.current_sid, name=row.name)

    async def get_by_email(self, email: str) -> User | None:
        async with self.sessionmaker() as s:
            row = (await s.execute(select(UserRow).where(UserRow.email == email.lower()))).scalar_one_or_none()
            return await self._to_domain(row)

    async def get_by_id(self, user_id: str) -> User | None:
        async with self.sessionmaker() as s:
            return await self._to_domain(await s.get(UserRow, user_id))

    async def list_by_tenant(self, tenant: str) -> list[User]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(UserRow).where(UserRow.tenant_id == tenant))).scalars().all()
            return [await self._to_domain(r) for r in rows]

    async def list_all(self) -> list[UserDirectoryEntry]:
        # Cross-tenant: the platform-admin user directory ONLY. Deliberately unfiltered, ordered by
        # email so the directory is stable across pages.
        #
        # A COLUMN PROJECTION, not select(UserRow): the full entity would run _to_domain per row,
        # which decrypts every TOTP secret (Fernet, on the event loop) and materialises every password
        # hash, to render twenty rows that contain neither. It also means a row whose ciphertext no
        # longer decrypts after a key rotation cannot fail this endpoint.
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(
                UserRow.id, UserRow.email, UserRow.name, UserRow.tenant_id, UserRow.role,
                UserRow.twofa_enabled).order_by(UserRow.email))).all()
            return [UserDirectoryEntry(id=row.id, email=row.email, name=row.name,
                                       tenant=row.tenant_id, role=Role(row.role),
                                       twofa_enabled=row.twofa_enabled) for row in rows]

    async def set_sid(self, user_id: str, sid: str | None) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                row.current_sid = sid

    async def set_sid_if_password_hash(self, user_id: str, expected_password_hash: str, sid: str) -> bool:
        async with self.sessionmaker() as session, session.begin():
            result = await session.execute(update(UserRow).where(
                UserRow.id == user_id, UserRow.password_hash == expected_password_hash
            ).values(current_sid=sid))
            return result.rowcount == 1

    async def rotate_sid(self, user_id: str, expected_sid: str, new_sid: str) -> bool:
        async with self.sessionmaker() as session, session.begin():
            result = await session.execute(update(UserRow).where(
                UserRow.id == user_id, UserRow.current_sid == expected_sid
            ).values(current_sid=new_sid))
            return result.rowcount == 1

    async def enable_twofa(self, user_id: str, secret: str,
                           backup_code_hashes: dict[str, str] | None = None) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                row.twofa_enabled = True
                row.totp_secret = _encrypt_totp(secret)
                await s.execute(delete(MfaBackupCodeRow).where(MfaBackupCodeRow.user_id == user_id))
                s.add_all(MfaBackupCodeRow(user_id=user_id, selector=selector, code_hash=code_hash)
                          for selector, code_hash in (backup_code_hashes or {}).items())

    async def consume_backup_code(self, user_id: str, code: str) -> bool:
        selector = twofa.backup_code_selector(code)
        if not selector:
            return False
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(MfaBackupCodeRow, (user_id, selector))
            if row is None or not verify_password(twofa.normalize_backup_code(code), row.code_hash):
                return False
            result = await s.execute(delete(MfaBackupCodeRow).where(
                MfaBackupCodeRow.user_id == user_id,
                MfaBackupCodeRow.selector == selector,
                MfaBackupCodeRow.code_hash == row.code_hash,
            ))
            return result.rowcount == 1

    async def set_password(self, user_id: str, password_hash: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                row.password_hash = password_hash

    async def set_password_and_revoke_sessions(self, user_id: str, password_hash: str) -> bool:
        async with self.sessionmaker() as session, session.begin():
            result = await session.execute(update(UserRow).where(
                UserRow.id == user_id
            ).values(password_hash=password_hash, current_sid=None))
            return result.rowcount == 1

    async def set_name(self, user_id: str, name: str | None) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                row.name = name

    async def set_role(self, user_id: str, role: Role) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                row.role = role.value

    async def delete(self, user_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(UserRow, user_id)
            if row:
                await s.delete(row)


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

    async def add_for_enabled_agent(
        self, tenant: str, agent_id: str, topic: str, text: str,
        recheck_worker,
    ) -> None:
        text = (text or "").strip()
        if not text:
            return
        async with self.sessionmaker() as session, session.begin():
            agent = (await session.execute(
                select(AgentRow).where(
                    AgentRow.tenant_id == tenant, AgentRow.id == agent_id
                ).with_for_update()
            )).scalar_one_or_none()
            if agent is None or not agent.enabled:
                raise WorkerUnavailable
            exists = (await session.execute(
                select(VerifiedAnswer.id).where(
                    VerifiedAnswer.tenant_id == tenant,
                    VerifiedAnswer.topic == topic,
                    VerifiedAnswer.body == text,
                ).limit(1)
            )).scalar_one_or_none()
            if exists is None:
                session.add(VerifiedAnswer(tenant_id=tenant, topic=topic, body=text))

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
            s.add(PassageRow(id=passage.id, tenant_id=passage.tenant, agent_id=passage.agent_id,
                             doc_id=passage.doc_id, text=passage.text, embedding=passage.embedding))

    async def get(self, tenant: str, agent_id: str | None = None) -> list[Passage]:
        async with self.sessionmaker() as s:
            stmt = select(PassageRow).where(PassageRow.tenant_id == tenant)
            if agent_id is not None:
                stmt = stmt.where(PassageRow.agent_id == agent_id)
            rows = (await s.execute(stmt)).scalars().all()
            return [Passage(id=r.id, tenant=r.tenant_id, doc_id=r.doc_id, text=r.text,
                            embedding=list(r.embedding or []), agent_id=r.agent_id) for r in rows]

    async def delete_doc(self, tenant: str, doc_id: str, agent_id: str | None = None) -> int:
        async with self.sessionmaker() as s, s.begin():
            stmt = delete(PassageRow).where(PassageRow.tenant_id == tenant, PassageRow.doc_id == doc_id)
            if agent_id is not None:
                stmt = stmt.where(PassageRow.agent_id == agent_id)
            result = await s.execute(stmt)
            return result.rowcount or 0


@dataclass
class SqlAgentStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: AgentRow) -> Agent:
        return Agent(id=r.id, tenant=r.tenant_id, name=r.name, atype=r.atype,
                     status=r.status, config=dict(r.config or {}), created_at=r.created_at,
                     enabled=r.enabled)

    @staticmethod
    def _row(agent: Agent) -> AgentRow:
        return AgentRow(id=agent.id, tenant_id=agent.tenant, name=agent.name,
                        atype=agent.atype, status=agent.status, config=agent.config,
                        created_at=agent.created_at, enabled=agent.enabled)

    async def add(self, agent: Agent) -> Agent:
        async with self.sessionmaker() as s, s.begin():
            s.add(self._row(agent))
        return agent

    async def add_with_limit(self, agent: Agent, worker_limit: int) -> Agent:
        async with self.sessionmaker() as s, s.begin():
            tenant = (await s.execute(
                select(TenantRow).where(TenantRow.id == agent.tenant).with_for_update()
            )).scalar_one_or_none()
            if tenant is None:
                raise KeyError(agent.tenant)
            count = (await s.execute(
                select(func.count()).select_from(AgentRow)
                .where(AgentRow.tenant_id == agent.tenant)
            )).scalar_one()
            if worker_limit >= 0 and count >= worker_limit:
                raise PlanLimitError(f"worker limit {worker_limit} reached")
            s.add(self._row(agent))
        return agent

    async def list(self, tenant: str) -> list[Agent]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(AgentRow).where(AgentRow.tenant_id == tenant))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def count(self, tenant: str) -> int:
        async with self.sessionmaker() as s:
            return (await s.execute(
                select(func.count()).select_from(AgentRow).where(AgentRow.tenant_id == tenant)
            )).scalar_one()

    async def get(self, tenant: str, agent_id: str) -> Agent | None:
        async with self.sessionmaker() as s:
            row = await s.get(AgentRow, agent_id)
            if row is None or row.tenant_id != tenant:
                return None
            return self._to_domain(row)

    async def list_all(self) -> list[Agent]:
        # Cross-tenant: the platform-admin worker directory ONLY. Ordered by tenant then id so the
        # directory is stable across pages.
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(AgentRow).order_by(AgentRow.tenant_id, AgentRow.id))).scalars().all()
            return [self._to_domain(row) for row in rows]

    async def get_by_id(self, agent_id: str) -> Agent | None:
        # Global (tenant-agnostic) lookup for the PUBLIC chat path only (agent ids are globally
        # unique PKs). Callers must gate on status == "ready" and expose only public fields.
        async with self.sessionmaker() as s:
            row = await s.get(AgentRow, agent_id)
            return self._to_domain(row) if row is not None else None

    async def set_status(self, tenant: str, agent_id: str, status: str) -> Agent | None:
        # Tenant-filtered like every other store method; the admin endpoint resolves the tenant first.
        async with self.sessionmaker() as s, s.begin():
            row = (await s.execute(select(AgentRow).where(
                AgentRow.tenant_id == tenant, AgentRow.id == agent_id).with_for_update()
            )).scalar_one_or_none()
            if row is None:
                return None
            row.status = status
            return self._to_domain(row)

    async def mark_ready(self, tenant: str, agent_id: str) -> Agent:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(AgentRow, agent_id)
            if row is None or row.tenant_id != tenant:
                raise KeyError(agent_id)
            row.status = "ready"
            return self._to_domain(row)

    async def update_config(self, tenant: str, agent_id: str, patch: dict, *,
                            audit: Callable[[dict], dict] | None = None) -> Agent:
        """Merge-patch the config, optionally writing an audit row in the SAME transaction.

        `audit` receives the previous config, taken under the row lock, and returns the row to write.
        A callback rather than a prepared row because of a bug this shape prevents: a caller that read
        the agent beforehand to capture its old state was holding a LIVE reference that the update
        then mutated, so every credential audit reported that nothing had changed. Snapshotting inside
        the transaction makes that impossible rather than merely fixed.

        Writing the row here rather than afterwards is the discipline set_enabled already uses: a
        credential rotation cannot land without a record of who performed it.
        """
        async with self.sessionmaker() as s, s.begin():
            row = (await s.execute(
                select(AgentRow).where(AgentRow.tenant_id == tenant, AgentRow.id == agent_id)
                .with_for_update()
            )).scalar_one_or_none()
            if row is None:
                raise KeyError(agent_id)
            previous = dict(row.config or {})
            row.config = {**previous, **patch}
            if audit is not None:
                s.add(AuditEventRow(**audit(previous)))
            return self._to_domain(row)

    async def set_enabled(self, tenant: str, agent_id: str, enabled: bool, *,
                          changed_by_email: str, reason: str | None) -> Agent:
        async with self.sessionmaker() as s, s.begin():
            row = (await s.execute(
                select(AgentRow).where(
                    AgentRow.tenant_id == tenant, AgentRow.id == agent_id
                ).with_for_update()
            )).scalar_one_or_none()
            if row is None:
                raise KeyError(agent_id)
            if row.enabled == enabled:
                return self._to_domain(row)
            previous = row.enabled
            row.enabled = enabled
            s.add(AgentStateAuditRow(
                tenant_id=tenant, agent_id=agent_id, changed_by_email=changed_by_email,
                previous_enabled=previous, enabled=enabled,
                reason=(reason or "").strip() or None))
            # Also into the unified stream, in the SAME transaction, so the row-locked guarantee this
            # method already had extends to it: an availability change cannot land without either record.
            #
            # Both are written rather than one. agent_state_audit is still read by the customer detail
            # view and its shape (previous_enabled, enabled) is what that UI renders, so removing it
            # would be a UI change bundled into a data change. What matters for "one stream" is that the
            # unified trail is complete, not that the old table is gone; retiring it is a follow-up once
            # nothing reads it.
            s.add(AuditEventRow(**_worker_availability_row(
                tenant=tenant, agent_id=agent_id, name=row.name,
                changed_by_email=changed_by_email, previous=previous, enabled=enabled,
                reason=(reason or "").strip() or None)))
            return self._to_domain(row)

    async def list_state_audit(self, tenant: str, *, limit: int = 50) -> list[AgentStateAudit]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(AgentStateAuditRow)
                .where(AgentStateAuditRow.tenant_id == tenant)
                .order_by(AgentStateAuditRow.created_at.desc(), AgentStateAuditRow.id.desc())
                .limit(max(1, min(limit, 200)))
            )).scalars().all()
            return [AgentStateAudit(
                id=row.id, tenant=row.tenant_id, agent_id=row.agent_id,
                changed_by_email=row.changed_by_email,
                previous_enabled=row.previous_enabled, enabled=row.enabled,
                reason=row.reason, created_at=row.created_at) for row in rows]


async def _lock_enabled_pack(
    session: AsyncSession, tenant: str, pack_id: str, *, agent_id: str | None = None,
) -> RfpPackRow:
    pack = (await session.execute(
        select(RfpPackRow).where(
            RfpPackRow.tenant_id == tenant, RfpPackRow.id == pack_id
        ).with_for_update()
    )).scalar_one_or_none()
    if pack is None or (agent_id is not None and pack.agent_id != agent_id):
        raise RfpPackNotFound(pack_id)
    agent = (await session.execute(
        select(AgentRow).where(
            AgentRow.tenant_id == tenant, AgentRow.id == pack.agent_id
        ).with_for_update()
    )).scalar_one_or_none()
    if agent is None or not agent.enabled:
        raise WorkerUnavailable
    return pack


async def _lock_enabled_agent(
    session: AsyncSession, tenant: str, agent_id: str,
) -> AgentRow:
    agent = (await session.execute(
        select(AgentRow).where(
            AgentRow.tenant_id == tenant, AgentRow.id == agent_id
        ).with_for_update()
    )).scalar_one_or_none()
    if agent is None or not agent.enabled:
        raise WorkerUnavailable
    return agent


@dataclass
class SqlRfpPackStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: RfpPackRow) -> RfpPack:
        return RfpPack(id=r.id, tenant=r.tenant_id, agent_id=r.agent_id, title=r.title,
                       client_name=r.client_name, deadline=r.deadline, stage=r.stage,
                       created_at=r.created_at, document_text=r.document_text or "",
                       source_documents=list(r.source_documents or []),
                       outcome=r.outcome, outcome_reason=r.outcome_reason or "",
                       outcome_value=r.outcome_value, outcome_at=r.outcome_at,
                       brief=r.brief, compliance=r.compliance, gen_status=r.gen_status)

    async def add(self, pack: RfpPack) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, pack.tenant, pack.agent_id)
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
            row = await _lock_enabled_pack(s, tenant, pack_id)
            row.stage = stage
            return self._to_domain(row)

    async def set_document_text(self, tenant: str, pack_id: str, text: str) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await _lock_enabled_pack(s, tenant, pack_id)
            row.document_text = text
            return self._to_domain(row)

    async def set_source_documents(self, tenant: str, pack_id: str, docs: list) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await _lock_enabled_pack(s, tenant, pack_id)
            row.source_documents = list(docs or [])
            return self._to_domain(row)

    async def set_outcome(self, tenant: str, pack_id: str, *, outcome: str | None,
                          reason: str, value: float | None) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await _lock_enabled_pack(s, tenant, pack_id)
            row.outcome, row.outcome_reason, row.outcome_value = outcome, reason, value
            row.outcome_at = datetime.now(timezone.utc) if outcome else None
            return self._to_domain(row)

    async def set_outcome_for_enabled_agent(
        self, tenant: str, pack_id: str, agent_id: str, *, outcome: str | None,
        reason: str, value: float | None, recheck_worker,
    ) -> RfpPack:
        async with self.sessionmaker() as session, session.begin():
            agent = (await session.execute(
                select(AgentRow).where(
                    AgentRow.tenant_id == tenant, AgentRow.id == agent_id
                ).with_for_update()
            )).scalar_one_or_none()
            if agent is None or not agent.enabled:
                raise WorkerUnavailable
            row = (await session.execute(
                select(RfpPackRow).where(
                    RfpPackRow.tenant_id == tenant, RfpPackRow.id == pack_id,
                    RfpPackRow.agent_id == agent_id,
                ).with_for_update()
            )).scalar_one_or_none()
            if row is None:
                raise RfpPackNotFound(pack_id)
            row.outcome, row.outcome_reason, row.outcome_value = outcome, reason, value
            row.outcome_at = datetime.now(timezone.utc) if outcome else None
            return self._to_domain(row)

    async def set_brief(self, tenant: str, pack_id: str, brief: dict | None) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await _lock_enabled_pack(s, tenant, pack_id)
            row.brief = brief
            return self._to_domain(row)

    async def set_compliance(self, tenant: str, pack_id: str, items: list | None) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await _lock_enabled_pack(s, tenant, pack_id)
            row.compliance = items
            return self._to_domain(row)

    async def set_gen_status(self, tenant: str, pack_id: str, status: dict | None) -> RfpPack:
        async with self.sessionmaker() as s, s.begin():
            row = await _lock_enabled_pack(s, tenant, pack_id)
            row.gen_status = status
            return self._to_domain(row)

    async def delete(self, tenant: str, pack_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await _lock_enabled_pack(s, tenant, pack_id)
            await s.delete(row)


@dataclass
class SqlRequirementStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: PackRequirementRow) -> PackRequirement:
        return PackRequirement(id=r.id, tenant=r.tenant_id, pack_id=r.pack_id, req_id=r.req_id,
                               title=r.title, classification=r.classification, requirement=r.requirement)

    async def replace_all(self, tenant: str, pack_id: str, items: list[PackRequirement]) -> list[PackRequirement]:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_pack(s, tenant, pack_id)
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
            await _lock_enabled_pack(s, tenant, pack_id)
            await s.execute(delete(PackRequirementRow).where(
                PackRequirementRow.tenant_id == tenant, PackRequirementRow.pack_id == pack_id))


@dataclass
class SqlPackSectionStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: PackSectionRow) -> PackSection:
        return PackSection(id=r.id, tenant=r.tenant_id, pack_id=r.pack_id, code=r.code, name=r.name,
                           page=r.page, weighting=r.weighting, status=r.status, parent_id=r.parent_id,
                           assigned_reviewer_user_id=r.assigned_reviewer_user_id,
                           assigned_reviewer_name=r.assigned_reviewer_name or "",
                           reviewer=r.reviewer, reviewer_name=r.reviewer_name or "", due_date=r.due_date,
                           manual=r.manual, kb_gap=r.kb_gap, order_index=r.order_index)

    async def add(self, section: PackSection) -> PackSection:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_pack(s, section.tenant, section.pack_id)
            s.add(PackSectionRow(id=section.id, tenant_id=section.tenant, pack_id=section.pack_id,
                                 code=section.code, name=section.name, page=section.page,
                                 weighting=section.weighting, status=section.status, parent_id=section.parent_id,
                                 assigned_reviewer_user_id=section.assigned_reviewer_user_id,
                                 assigned_reviewer_name=section.assigned_reviewer_name,
                                 reviewer=section.reviewer, reviewer_name=section.reviewer_name,
                                 due_date=section.due_date,
                                 manual=section.manual, kb_gap=section.kb_gap, order_index=section.order_index))
        return section

    async def list(self, tenant: str, pack_id: str) -> list[PackSection]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(PackSectionRow).where(
                PackSectionRow.tenant_id == tenant, PackSectionRow.pack_id == pack_id)
                .order_by(PackSectionRow.order_index))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def get(self, tenant: str, section_id: str) -> PackSection | None:
        async with self.sessionmaker() as s:
            row = await s.get(PackSectionRow, section_id)
            if row is None or row.tenant_id != tenant:
                return None
            return self._to_domain(row)

    async def update(self, tenant: str, section_id: str, **fields) -> PackSection:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PackSectionRow, section_id)
            if row is None or row.tenant_id != tenant:
                raise PackSectionNotFound(section_id)
            await _lock_enabled_pack(s, tenant, row.pack_id)
            for k, v in fields.items():
                setattr(row, k, v)
            return self._to_domain(row)

    async def delete(self, tenant: str, section_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PackSectionRow, section_id)
            if row is not None and row.tenant_id == tenant:
                await _lock_enabled_pack(s, tenant, row.pack_id)
                await s.delete(row)

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_pack(s, tenant, pack_id)
            await s.execute(delete(PackSectionRow).where(
                PackSectionRow.tenant_id == tenant, PackSectionRow.pack_id == pack_id))


@dataclass
class SqlPackQuestionStore:
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: PackQuestionRow) -> PackQuestion:
        return PackQuestion(id=r.id, tenant=r.tenant_id, pack_id=r.pack_id, section_id=r.section_id,
                            text=r.text, req_id=r.req_id or "", word_limit=r.word_limit,
                            ai_answer=r.ai_answer or "", ai_sources=list(r.ai_sources or []),
                            confidence=r.confidence, grounding=r.grounding, gaps=r.gaps or "",
                            decision=r.decision or "", kb_gap=r.kb_gap,
                            locked=r.locked, user_draft=r.user_draft or "", order_index=r.order_index)

    async def add(self, question: PackQuestion) -> PackQuestion:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_pack(s, question.tenant, question.pack_id)
            s.add(PackQuestionRow(id=question.id, tenant_id=question.tenant, pack_id=question.pack_id,
                                  section_id=question.section_id, text=question.text, req_id=question.req_id,
                                  word_limit=question.word_limit, ai_answer=question.ai_answer,
                                  ai_sources=question.ai_sources, confidence=question.confidence,
                                  grounding=question.grounding, gaps=question.gaps,
                                  decision=question.decision, kb_gap=question.kb_gap, locked=question.locked,
                                  user_draft=question.user_draft, order_index=question.order_index))
        return question

    async def list(self, tenant: str, pack_id: str) -> list[PackQuestion]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(PackQuestionRow).where(
                PackQuestionRow.tenant_id == tenant, PackQuestionRow.pack_id == pack_id)
                .order_by(PackQuestionRow.order_index))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def list_for_section(self, tenant: str, section_id: str) -> list[PackQuestion]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(PackQuestionRow).where(
                PackQuestionRow.tenant_id == tenant, PackQuestionRow.section_id == section_id)
                .order_by(PackQuestionRow.order_index))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def get(self, tenant: str, question_id: str) -> PackQuestion | None:
        async with self.sessionmaker() as s:
            row = await s.get(PackQuestionRow, question_id)
            if row is None or row.tenant_id != tenant:
                return None
            return self._to_domain(row)

    async def update(self, tenant: str, question_id: str, **fields) -> PackQuestion:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PackQuestionRow, question_id)
            if row is None or row.tenant_id != tenant:
                raise PackQuestionNotFound(question_id)
            await _lock_enabled_pack(s, tenant, row.pack_id)
            for k, v in fields.items():
                setattr(row, k, v)
            return self._to_domain(row)

    async def delete(self, tenant: str, question_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PackQuestionRow, question_id)
            if row is not None and row.tenant_id == tenant:
                await _lock_enabled_pack(s, tenant, row.pack_id)
                await s.delete(row)

    async def delete_for_section(self, tenant: str, section_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            section = await s.get(PackSectionRow, section_id)
            if section is None or section.tenant_id != tenant:
                raise PackSectionNotFound(section_id)
            await _lock_enabled_pack(s, tenant, section.pack_id)
            await s.execute(delete(PackQuestionRow).where(
                PackQuestionRow.tenant_id == tenant, PackQuestionRow.section_id == section_id))

    async def delete_for_pack(self, tenant: str, pack_id: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_pack(s, tenant, pack_id)
            await s.execute(delete(PackQuestionRow).where(
                PackQuestionRow.tenant_id == tenant, PackQuestionRow.pack_id == pack_id))


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
            await _lock_enabled_pack(s, tenant, pack_id)
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
            await _lock_enabled_pack(s, tenant, pack_id)
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
            await _lock_enabled_pack(s, a.tenant, a.pack_id, agent_id=a.agent_id)
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
            await _lock_enabled_pack(s, tenant, row.pack_id, agent_id=row.agent_id)
            for k, v in fields.items():
                setattr(row, k, v)
            return self._to_domain(row)

    async def delete_by_section(self, tenant: str, pack_id: str, section_id: str) -> int:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_pack(s, tenant, pack_id)
            result = await s.execute(delete(AssignmentRow).where(
                AssignmentRow.tenant_id == tenant, AssignmentRow.pack_id == pack_id,
                AssignmentRow.section_id == section_id))
            return result.rowcount or 0

    async def delete_by_pack(self, tenant: str, pack_id: str) -> int:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_pack(s, tenant, pack_id)
            result = await s.execute(delete(AssignmentRow).where(
                AssignmentRow.tenant_id == tenant, AssignmentRow.pack_id == pack_id))
            return result.rowcount or 0


@dataclass
class SqlChatStore:
    """Postgres-backed chat history (Conversation/Message tables), tenant-scoped."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def ensure(
        self, tenant: str, conversation_id: str, *, user_id: str = "", agent_id: str = "",
        crm_eligible: bool = False,
    ) -> None:
        async with self.sessionmaker() as s, s.begin():
            if await s.get(ConversationRow, conversation_id) is None:
                s.add(ConversationRow(
                    id=conversation_id, tenant_id=tenant, user_id=user_id or "public",
                    agent_id=agent_id or "public", crm_eligible=crm_eligible))

    async def _lock_enabled_agent(self, session: AsyncSession, tenant: str, agent_id: str) -> None:
        agent = (await session.execute(
            select(AgentRow).where(
                AgentRow.tenant_id == tenant, AgentRow.id == agent_id
            ).with_for_update()
        )).scalar_one_or_none()
        if agent is None or not agent.enabled:
            raise WorkerUnavailable

    async def _ensure_conversation_scope(
        self, session: AsyncSession, tenant: str, conversation_id: str, *,
        user_id: str, agent_id: str, crm_eligible: bool,
    ) -> None:
        row = (await session.execute(
            select(ConversationRow).where(
                ConversationRow.id == conversation_id
            ).with_for_update()
        )).scalar_one_or_none()
        if row is None:
            session.add(ConversationRow(
                id=conversation_id, tenant_id=tenant, user_id=user_id or "public",
                agent_id=agent_id, crm_eligible=crm_eligible))
        elif row.tenant_id != tenant or row.agent_id != agent_id:
            raise ConversationScopeError

    async def ensure_for_enabled_agent(
        self, tenant: str, conversation_id: str, *, user_id: str, agent_id: str,
        crm_eligible: bool = False, recheck_worker,
    ) -> None:
        async with self.sessionmaker() as session, session.begin():
            await self._lock_enabled_agent(session, tenant, agent_id)
            await self._ensure_conversation_scope(
                session, tenant, conversation_id, user_id=user_id, agent_id=agent_id,
                crm_eligible=crm_eligible)

    async def append(self, tenant: str, conversation_id: str, role: str, text: str) -> Message:
        await self.ensure(tenant, conversation_id)
        async with self.sessionmaker() as s, s.begin():
            s.add(MessageRow(conversation_id=conversation_id, tenant_id=tenant, role=role, body=text))
        return Message(role=role, text=text)

    async def append_exchange_for_enabled_agent(
        self, tenant: str, conversation_id: str, *, user_id: str, agent_id: str,
        crm_eligible: bool = False, user_text: str, assistant_text: str, recheck_worker,
    ) -> Message:
        async with self.sessionmaker() as session, session.begin():
            await self._lock_enabled_agent(session, tenant, agent_id)
            await self._ensure_conversation_scope(
                session, tenant, conversation_id, user_id=user_id, agent_id=agent_id,
                crm_eligible=crm_eligible)
            session.add_all([
                MessageRow(
                    conversation_id=conversation_id, tenant_id=tenant,
                    role="user", body=user_text),
                MessageRow(
                    conversation_id=conversation_id, tenant_id=tenant,
                    role="assistant", body=assistant_text),
            ])
        return Message(role="assistant", text=assistant_text)

    async def history(self, tenant: str, conversation_id: str, *, limit: int = 20) -> list[Message]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(MessageRow).where(MessageRow.tenant_id == tenant,
                                         MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.id))).scalars().all()
            msgs = [Message(role=r.role, text=r.body, created_at=r.created_at) for r in rows]
            return msgs[-limit:] if limit else msgs

    async def clear(self, tenant: str, conversation_id: str) -> int:
        async with self.sessionmaker() as s, s.begin():
            result = await s.execute(delete(MessageRow).where(
                MessageRow.tenant_id == tenant, MessageRow.conversation_id == conversation_id))
            # Returned so the audit does not have to read the conversation to count it. history()
            # defaults to a 20-row window and has no SQL LIMIT, so counting that way both saturated at
            # 20 and materialised every message body to do it.
            return result.rowcount or 0

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[ConversationSummary]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(ConversationRow).where(ConversationRow.tenant_id == tenant,
                                              ConversationRow.agent_id == agent_id)
                .order_by(ConversationRow.created_at))).scalars().all()
            return [ConversationSummary(
                id=r.id, user_id=r.user_id, agent_id=r.agent_id,
                crm_eligible=r.crm_eligible, created_at=r.created_at)
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

    async def get_identity(self, email: str) -> AdminIdentity | None:
        async with self.sessionmaker() as s:
            row = await s.get(PlatformAdminRow, email.lower())
            return self._to_identity(row) if row else None

    async def list_admins(self) -> list[AdminIdentity]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(PlatformAdminRow).order_by(PlatformAdminRow.email)
            )).scalars().all()
            return [self._to_identity(row) for row in rows]

    async def grant(self, email: str, role: AdminRole,
                    capabilities: frozenset[Capability] | None, *,
                    changed_by_email: str, reason: str | None) -> AdminIdentity:
        """Row-locked upsert plus one audit row, in a single transaction.

        Same shape as SqlAgentStore.set_enabled: SELECT ... FOR UPDATE on the target, capture the
        previous values before mutating, and write the audit row inside the same transaction so a
        grant can never land without its audit entry. A no-op change writes no audit row.
        """
        key = email.lower()
        # Persist the EFFECTIVE set: a super_admin implicitly keeps manage_admins, and storing the
        # requested list without it made platform_admins and the audit under-report the real
        # authority while GET /admin/org reported the effective one.
        stored = (sorted(c.value for c in effective_capabilities(role, capabilities))
                  if capabilities is not None else None)
        async with self.sessionmaker() as s, s.begin():
            row = (await s.execute(
                select(PlatformAdminRow).where(PlatformAdminRow.email == key).with_for_update()
            )).scalar_one_or_none()
            previous_role = row.role if row else None
            previous_caps = list(row.capabilities) if row and row.capabilities is not None else None
            if row is None:
                row = PlatformAdminRow(email=key, role=role.value, capabilities=stored)
                s.add(row)
            else:
                row.role = role.value
                row.capabilities = stored
            unchanged = previous_role == role.value and previous_caps == stored
            if not unchanged:
                # Same transaction as the grant, matching what this method already guaranteed for the
                # legacy row. See set_enabled for why both are written.
                s.add(AuditEventRow(**_platform_access_row(
                    email=key, actor_email=changed_by_email, previous_role=previous_role,
                    role=role.value, previous_capabilities=previous_caps, capabilities=stored,
                    reason=(reason or "").strip() or None)))
                s.add(PlatformAdminAuditRow(
                    email=key, changed_by_email=changed_by_email,
                    previous_role=previous_role, role=role.value,
                    previous_capabilities=previous_caps, capabilities=stored,
                    reason=(reason or "").strip() or None))
            return AdminIdentity(email=key, role=role,
                                 capabilities=effective_capabilities(role, capabilities))

    async def revoke(self, email: str, *, changed_by_email: str, reason: str | None) -> None:
        key = email.lower()
        async with self.sessionmaker() as s, s.begin():
            row = (await s.execute(
                select(PlatformAdminRow).where(PlatformAdminRow.email == key).with_for_update()
            )).scalar_one_or_none()
            if row is None:
                return
            previous_caps = list(row.capabilities) if row.capabilities is not None else None
            # Same transaction as the delete, so a revoked admin cannot vanish without a record of who
            # revoked them. Read off the row BEFORE the delete: afterwards the role and capability set
            # are unrecoverable, which is the same ordering the tenant hard delete had to get right.
            s.add(AuditEventRow(**_platform_access_row(
                email=key, actor_email=changed_by_email, previous_role=row.role, role=None,
                previous_capabilities=previous_caps, capabilities=None,
                reason=(reason or "").strip() or None)))
            s.add(PlatformAdminAuditRow(
                email=key, changed_by_email=changed_by_email,
                previous_role=row.role, role=None,
                previous_capabilities=previous_caps,
                capabilities=None, reason=(reason or "").strip() or None))
            await s.delete(row)

    async def list_audit(self, *, limit: int = 50) -> list[AdminGrantAudit]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(PlatformAdminAuditRow)
                .order_by(PlatformAdminAuditRow.created_at.desc(), PlatformAdminAuditRow.id.desc())
                .limit(max(1, min(limit, 200)))
            )).scalars().all()
            return [AdminGrantAudit(
                id=row.id, email=row.email, changed_by_email=row.changed_by_email,
                previous_role=row.previous_role, role=row.role,
                previous_capabilities=row.previous_capabilities, capabilities=row.capabilities,
                reason=row.reason, created_at=row.created_at) for row in rows]

    @staticmethod
    def _to_identity(row) -> AdminIdentity:
        role = AdminRole(row.role)
        explicit = read_capabilities(row.capabilities) if row.capabilities is not None else None
        return AdminIdentity(email=row.email, role=role,
                             capabilities=effective_capabilities(role, explicit))


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
            await _lock_enabled_agent(s, contact.tenant, contact.agent_id)
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
                await _lock_enabled_agent(s, contact.tenant, contact.agent_id)
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

    def _to_domain(self, row: CrmActionRow) -> CrmAction:
        return CrmAction(
            id=row.id, tenant=row.tenant_id, contact_id=row.contact_id, title=row.title,
            action_type=row.action_type, description=row.description or "",
            priority=row.priority, status=row.status, created_at=row.created_at)

    async def get(self, tenant: str, action_id: str) -> CrmAction | None:
        async with self.sessionmaker() as session:
            row = await session.get(CrmActionRow, action_id)
            return self._to_domain(row) if row is not None and row.tenant_id == tenant else None

    async def add(self, action: CrmAction) -> CrmAction:
        async with self.sessionmaker() as s, s.begin():
            contact = await s.get(ContactRow, action.contact_id)
            if contact is None or contact.tenant_id != action.tenant:
                return action
            await _lock_enabled_agent(s, action.tenant, contact.agent_id)
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
            contact = await s.get(ContactRow, row.contact_id)
            if contact is None or contact.tenant_id != tenant:
                return None
            await _lock_enabled_agent(s, tenant, contact.agent_id)
            row.status = status
            return CrmAction(id=row.id, tenant=row.tenant_id, contact_id=row.contact_id, title=row.title,
                             action_type=row.action_type, description=row.description or "",
                             priority=row.priority, status=row.status, created_at=row.created_at)


# --- IDG Sales Intelligence (app.modules.sales_intelligence) ---------------------------------
# Postgres-backed replacements for the in-memory stores in
# app.modules.sales_intelligence.models, behind the same Protocols. Every query is tenant-scoped
# (BOLA-safe) exactly like the CRM stores above.


def _ingestion_source_from_row(r: SalesIntelIngestionSourceRow) -> IngestionSource:
    return IngestionSource(
        id=r.id, tenant=r.tenant_id, agent_id=r.agent_id, source_key=r.source_key, name=r.name,
        type=r.type, status=r.status, auth_status=r.auth_status, scan_cadence=r.scan_cadence,
        last_scan_status=r.last_scan_status, last_scan_at=r.last_scan_at,
        opportunities_found=r.opportunities_found, last_error=r.last_error, config=dict(r.config or {}),
        created_at=r.created_at, updated_at=r.updated_at)


@dataclass
class SqlIngestionSourceStore:
    """Persists UNGM/TED ingestion-source config per worker -- previously in-memory only, so the
    enabled/disabled state and last-scan metadata were wiped on every redeploy."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def get_or_create(self, tenant: str, agent_id: str, source_key: str, defaults: dict) -> IngestionSource:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, tenant, agent_id)
            row = (await s.execute(select(SalesIntelIngestionSourceRow).where(
                SalesIntelIngestionSourceRow.tenant_id == tenant,
                SalesIntelIngestionSourceRow.agent_id == agent_id,
                SalesIntelIngestionSourceRow.source_key == source_key))).scalars().first()
            if row is None:
                row = SalesIntelIngestionSourceRow(id=uuid.uuid4().hex[:12], tenant_id=tenant, agent_id=agent_id,
                                                   source_key=source_key, **defaults)
                s.add(row)
                await s.flush()
            return _ingestion_source_from_row(row)

    async def get(self, tenant: str, agent_id: str, source_key: str) -> IngestionSource | None:
        async with self.sessionmaker() as s:
            row = (await s.execute(select(SalesIntelIngestionSourceRow).where(
                SalesIntelIngestionSourceRow.tenant_id == tenant,
                SalesIntelIngestionSourceRow.agent_id == agent_id,
                SalesIntelIngestionSourceRow.source_key == source_key))).scalars().first()
            return _ingestion_source_from_row(row) if row else None

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[IngestionSource]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(SalesIntelIngestionSourceRow).where(
                SalesIntelIngestionSourceRow.tenant_id == tenant,
                SalesIntelIngestionSourceRow.agent_id == agent_id))).scalars().all()
            return [_ingestion_source_from_row(r) for r in rows]

    async def list_active(self, tenant: str | None = None) -> list[IngestionSource]:
        async with self.sessionmaker() as s:
            q = select(SalesIntelIngestionSourceRow).where(SalesIntelIngestionSourceRow.status == "active")
            if tenant is not None:
                q = q.where(SalesIntelIngestionSourceRow.tenant_id == tenant)
            rows = (await s.execute(q)).scalars().all()
            return [_ingestion_source_from_row(r) for r in rows]

    async def update(self, source: IngestionSource) -> IngestionSource:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, source.tenant, source.agent_id)
            row = await s.get(SalesIntelIngestionSourceRow, source.id)
            if row is not None and row.tenant_id == source.tenant:
                row.name, row.type, row.status = source.name, source.type, source.status
                row.auth_status, row.scan_cadence = source.auth_status, source.scan_cadence
                row.last_scan_status, row.last_scan_at = source.last_scan_status, source.last_scan_at
                row.opportunities_found, row.last_error = source.opportunities_found, source.last_error
                row.config, row.updated_at = source.config, source.updated_at
        return source

    async def delete(self, tenant: str, agent_id: str, source_key: str) -> bool:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, tenant, agent_id)
            row = (await s.execute(select(SalesIntelIngestionSourceRow).where(
                SalesIntelIngestionSourceRow.tenant_id == tenant,
                SalesIntelIngestionSourceRow.agent_id == agent_id,
                SalesIntelIngestionSourceRow.source_key == source_key))).scalars().first()
            if row is None:
                return False
            await s.delete(row)
            return True


def _opportunity_from_row(r: SalesIntelOpportunityRow) -> Opportunity:
    return Opportunity(
        id=r.id, tenant=r.tenant_id, agent_id=r.agent_id, external_id=r.external_id, source_key=r.source_key,
        source_name=r.source_name, source_url=r.source_url, title=r.title, buyer=r.buyer, country=r.country,
        region=r.region, category=r.category, estimated_value=r.estimated_value, currency=r.currency,
        published_at=r.published_at, deadline_at=r.deadline_at, stage=r.stage, recommendation=r.recommendation,
        qualification_score=r.qualification_score, confidence=r.confidence,
        competitor_readiness=r.competitor_readiness, qualification_summary=r.qualification_summary,
        qualification_reasons=list(r.qualification_reasons or []),
        qualification_dimensions=dict(r.qualification_dimensions or {}),
        qualification_recommendations=list(r.qualification_recommendations or []),
        rejection_reasons=list(r.rejection_reasons or []), risks=list(r.risks or []),
        missing_fields=list(r.missing_fields or []), human_review_status=r.human_review_status,
        human_review_notes=r.human_review_notes, reviewed_by_user_id=r.reviewed_by_user_id,
        reviewed_at=r.reviewed_at, assigned_reviewer_user_id=r.assigned_reviewer_user_id,
        assigned_reviewer_name=r.assigned_reviewer_name, assigned_by_user_id=r.assigned_by_user_id,
        assigned_at=r.assigned_at, updated_by=r.updated_by, archived_at=r.archived_at, archived_by=r.archived_by,
        deleted_at=r.deleted_at, deleted_by=r.deleted_by, salesforce_push_status=r.salesforce_push_status,
        salesforce_opportunity_id=r.salesforce_opportunity_id, salesforce_pushed_at=r.salesforce_pushed_at,
        salesforce_push_error=r.salesforce_push_error, raw_payload=dict(r.raw_payload or {}),
        created_at=r.created_at, updated_at=r.updated_at)


def _apply_opportunity_columns(row: SalesIntelOpportunityRow, o: Opportunity) -> None:
    row.source_name, row.source_url, row.title = o.source_name, o.source_url, o.title
    row.buyer, row.country, row.region, row.category = o.buyer, o.country, o.region, o.category
    row.estimated_value, row.currency = o.estimated_value, o.currency
    row.published_at, row.deadline_at = o.published_at, o.deadline_at
    row.stage, row.recommendation = o.stage, o.recommendation
    row.qualification_score, row.confidence = o.qualification_score, o.confidence
    row.competitor_readiness, row.qualification_summary = o.competitor_readiness, o.qualification_summary
    row.qualification_reasons, row.qualification_dimensions = o.qualification_reasons, o.qualification_dimensions
    row.qualification_recommendations = o.qualification_recommendations
    row.rejection_reasons, row.risks, row.missing_fields = o.rejection_reasons, o.risks, o.missing_fields
    row.human_review_status, row.human_review_notes = o.human_review_status, o.human_review_notes
    row.reviewed_by_user_id, row.reviewed_at = o.reviewed_by_user_id, o.reviewed_at
    row.assigned_reviewer_user_id, row.assigned_reviewer_name = o.assigned_reviewer_user_id, o.assigned_reviewer_name
    row.assigned_by_user_id, row.assigned_at = o.assigned_by_user_id, o.assigned_at
    row.updated_by = o.updated_by
    row.archived_at, row.archived_by = o.archived_at, o.archived_by
    row.deleted_at, row.deleted_by = o.deleted_at, o.deleted_by
    row.salesforce_push_status, row.salesforce_opportunity_id = o.salesforce_push_status, o.salesforce_opportunity_id
    row.salesforce_pushed_at, row.salesforce_push_error = o.salesforce_pushed_at, o.salesforce_push_error
    row.raw_payload, row.updated_at = o.raw_payload, o.updated_at


@dataclass
class SqlOpportunityStore:
    """Persists UNGM/TED tender opportunities per worker -- the ingestion/qualification/review
    pipeline's source of truth, previously lost on every redeploy when it was in-memory only."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def find_by_external_id(self, tenant: str, agent_id: str, source_key: str,
                                  external_id: str) -> Opportunity | None:
        async with self.sessionmaker() as s:
            row = (await s.execute(select(SalesIntelOpportunityRow).where(
                SalesIntelOpportunityRow.tenant_id == tenant, SalesIntelOpportunityRow.agent_id == agent_id,
                SalesIntelOpportunityRow.source_key == source_key,
                SalesIntelOpportunityRow.external_id == external_id))).scalars().first()
            return _opportunity_from_row(row) if row else None

    async def add(self, opp: Opportunity) -> Opportunity:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, opp.tenant, opp.agent_id)
            row = SalesIntelOpportunityRow(id=opp.id, tenant_id=opp.tenant, agent_id=opp.agent_id,
                                           external_id=opp.external_id, source_key=opp.source_key,
                                           source_name=opp.source_name, created_at=opp.created_at)
            _apply_opportunity_columns(row, opp)
            s.add(row)
        return opp

    async def update(self, opp: Opportunity) -> Opportunity:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, opp.tenant, opp.agent_id)
            row = await s.get(SalesIntelOpportunityRow, opp.id)
            if row is not None and row.tenant_id == opp.tenant and row.agent_id == opp.agent_id:
                _apply_opportunity_columns(row, opp)
        return opp

    async def get(self, tenant: str, agent_id: str, opp_id: str) -> Opportunity | None:
        async with self.sessionmaker() as s:
            row = await s.get(SalesIntelOpportunityRow, opp_id)
            if row is None or row.tenant_id != tenant or row.agent_id != agent_id:
                return None
            return _opportunity_from_row(row)

    async def list_for_agent(self, tenant: str, agent_id: str, **filters) -> list[Opportunity]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(SalesIntelOpportunityRow).where(
                SalesIntelOpportunityRow.tenant_id == tenant,
                SalesIntelOpportunityRow.agent_id == agent_id))).scalars().all()
            items = [_opportunity_from_row(r) for r in rows]
            return _apply_opportunity_filters(items, filters)

    async def list_with_deadline(self) -> list[Opportunity]:
        # Cross-tenant: the deadline-reminder scheduler filters stage/threshold itself, so the
        # store only excludes archived/soft-deleted rows and those without a deadline.
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(SalesIntelOpportunityRow).where(
                SalesIntelOpportunityRow.deadline_at.is_not(None),
                SalesIntelOpportunityRow.archived_at.is_(None),
                SalesIntelOpportunityRow.deleted_at.is_(None)))).scalars().all()
            return [_opportunity_from_row(r) for r in rows]


@dataclass
class SqlActivityLogStore:
    """Persists the sales-intelligence audit trail (source status, scans, opportunity changes)
    per worker -- the history/scan-history views, previously in-memory only."""
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: SalesIntelActivityLogRow) -> ActivityLog:
        return ActivityLog(id=r.id, tenant=r.tenant_id, agent_id=r.agent_id, action=r.action,
                           opportunity_id=r.opportunity_id, actor_user_id=r.actor_user_id,
                           activity_type=r.activity_type, detail=r.detail, tone=r.tone,
                           metadata=dict(r.metadata_json or {}), created_at=r.created_at)

    async def add(self, log: ActivityLog) -> ActivityLog:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, log.tenant, log.agent_id)
            s.add(SalesIntelActivityLogRow(id=log.id, tenant_id=log.tenant, agent_id=log.agent_id,
                                           opportunity_id=log.opportunity_id, actor_user_id=log.actor_user_id,
                                           activity_type=log.activity_type, action=log.action, detail=log.detail,
                                           tone=log.tone, metadata_json=log.metadata, created_at=log.created_at))
        return log

    async def list_for_agent(self, tenant: str, agent_id: str, **filters) -> list[ActivityLog]:
        async with self.sessionmaker() as s:
            q = select(SalesIntelActivityLogRow).where(SalesIntelActivityLogRow.tenant_id == tenant,
                                                       SalesIntelActivityLogRow.agent_id == agent_id)
            if filters.get("opportunity_id"):
                q = q.where(SalesIntelActivityLogRow.opportunity_id == filters["opportunity_id"])
            if filters.get("activity_type"):
                q = q.where(SalesIntelActivityLogRow.activity_type == filters["activity_type"])
            if filters.get("action"):
                q = q.where(SalesIntelActivityLogRow.action == filters["action"])
            if filters.get("actions"):
                q = q.where(SalesIntelActivityLogRow.action.in_(list(filters["actions"])))
            q = q.order_by(SalesIntelActivityLogRow.created_at.desc())
            limit = filters.get("limit")
            if limit:
                q = q.limit(limit)
            rows = (await s.execute(q)).scalars().all()
            return [self._to_domain(r) for r in rows]


@dataclass
class SqlSalesforceConnectionStore:
    """Persists each worker's Salesforce OAuth connection (authorization_code + PKCE, with
    refresh). Access/refresh tokens arrive already Fernet-encrypted from the service layer
    (app.modules.sales_intelligence.salesforce, mirroring the Laravel model's `'encrypted'`
    cast), so the ciphertext is written verbatim into the enc_* columns and returned verbatim --
    no double-encryption. The service decrypts on use via app.core.crypto.decrypt."""
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: SalesIntelSalesforceConnectionRow) -> SalesforceConnection:
        return SalesforceConnection(tenant=r.tenant_id, agent_id=r.agent_id, status=r.status,
                                    instance_url=r.instance_url, access_token=r.enc_access_token,
                                    refresh_token=r.enc_refresh_token, token_type=r.token_type,
                                    token_expires_at=r.token_expires_at, salesforce_user_id=r.salesforce_user_id,
                                    salesforce_org_id=r.salesforce_org_id,
                                    connected_by_user_id=r.connected_by_user_id, last_error=r.last_error,
                                    connected_at=r.connected_at)

    async def get_or_create(self, tenant: str, agent_id: str) -> SalesforceConnection:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, tenant, agent_id)
            row = await s.get(SalesIntelSalesforceConnectionRow, (tenant, agent_id))
            if row is None:
                row = SalesIntelSalesforceConnectionRow(tenant_id=tenant, agent_id=agent_id)
                s.add(row)
                await s.flush()
            return self._to_domain(row)

    async def update(self, conn: SalesforceConnection) -> SalesforceConnection:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, conn.tenant, conn.agent_id)
            row = await s.get(SalesIntelSalesforceConnectionRow, (conn.tenant, conn.agent_id))
            if row is None:
                row = SalesIntelSalesforceConnectionRow(tenant_id=conn.tenant, agent_id=conn.agent_id)
                s.add(row)
            row.status, row.instance_url = conn.status, conn.instance_url
            row.enc_access_token, row.enc_refresh_token = conn.access_token, conn.refresh_token
            row.token_type, row.token_expires_at = conn.token_type, conn.token_expires_at
            row.salesforce_user_id, row.salesforce_org_id = conn.salesforce_user_id, conn.salesforce_org_id
            row.connected_by_user_id, row.last_error = conn.connected_by_user_id, conn.last_error
            row.connected_at = conn.connected_at
        return conn


@dataclass
class SqlIngestFilterSettingStore:
    """Persists the per-(tenant, agent) ingest filter (query toggle/keyword + allowlist bypass
    flags). One row per worker, tenant-scoped and BOLA-guarded exactly like the salesforce store."""
    sessionmaker: async_sessionmaker[AsyncSession]

    def _to_domain(self, r: SalesIntelIngestFilterRow) -> IngestFilterSetting:
        return IngestFilterSetting(tenant=r.tenant_id, agent_id=r.agent_id, query_enabled=r.query_enabled,
                                   query_keyword=r.query_keyword, all_countries=r.all_countries,
                                   all_categories=r.all_categories, updated_at=r.updated_at)

    async def get_or_create(self, tenant: str, agent_id: str) -> IngestFilterSetting:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, tenant, agent_id)
            row = await s.get(SalesIntelIngestFilterRow, (tenant, agent_id))
            if row is None:
                row = SalesIntelIngestFilterRow(tenant_id=tenant, agent_id=agent_id)
                s.add(row)
                await s.flush()
            return self._to_domain(row)

    async def update(self, setting: IngestFilterSetting) -> IngestFilterSetting:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, setting.tenant, setting.agent_id)
            row = await s.get(SalesIntelIngestFilterRow, (setting.tenant, setting.agent_id))
            if row is None:
                row = SalesIntelIngestFilterRow(tenant_id=setting.tenant, agent_id=setting.agent_id)
                s.add(row)
            row.query_enabled = setting.query_enabled
            row.query_keyword = setting.query_keyword
            row.all_countries = setting.all_countries
            row.all_categories = setting.all_categories
            row.updated_at = datetime.now(timezone.utc)
            await s.flush()
            return self._to_domain(row)


# --- Finance vertical (app.modules.finance) --------------------------------------------------
# Postgres-backed replacements for the in-memory finance stores, behind the same Protocols.
# Every query is tenant + agent scoped (BOLA-safe) exactly like the sales-intelligence stores.


def _finance_file_from_row(r: FinanceFileRow) -> FinanceFile:
    return FinanceFile(
        id=r.id, tenant=r.tenant_id, agent_id=r.agent_id, file_name=r.file_name,
        source_name=r.source_name, namespace=r.namespace, size_bytes=r.size_bytes,
        row_count=r.row_count, currency=r.currency, expense_rows=list(r.expense_rows or []),
        income_rows=list(r.income_rows or []), uploaded_at=r.uploaded_at)


@dataclass
class SqlFinanceFileStore:
    """Persists uploaded finance workbooks + their parsed rows per worker -- previously in-memory
    only, so the portfolio data and analytics were wiped on every redeploy."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, file: FinanceFile) -> FinanceFile:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, file.tenant, file.agent_id)
            s.add(FinanceFileRow(
                id=file.id, tenant_id=file.tenant, agent_id=file.agent_id, file_name=file.file_name,
                source_name=file.source_name, namespace=file.namespace, size_bytes=file.size_bytes,
                row_count=file.row_count, currency=file.currency, expense_rows=file.expense_rows,
                income_rows=file.income_rows, uploaded_at=file.uploaded_at))
        return file

    async def get(self, tenant: str, agent_id: str, file_id: str) -> FinanceFile | None:
        async with self.sessionmaker() as s:
            row = await s.get(FinanceFileRow, file_id)
            if row is None or row.tenant_id != tenant or row.agent_id != agent_id:
                return None
            return _finance_file_from_row(row)

    async def list_for_agent(self, tenant: str, agent_id: str) -> list[FinanceFile]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(FinanceFileRow).where(
                FinanceFileRow.tenant_id == tenant, FinanceFileRow.agent_id == agent_id
            ).order_by(FinanceFileRow.uploaded_at.desc()))).scalars().all()
            return [_finance_file_from_row(r) for r in rows]

    async def delete(self, tenant: str, agent_id: str, ids: list[str]) -> list[str]:
        deleted: list[str] = []
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, tenant, agent_id)
            for file_id in ids:
                row = await s.get(FinanceFileRow, file_id)
                if row is not None and row.tenant_id == tenant and row.agent_id == agent_id:
                    await s.delete(row)
                    deleted.append(file_id)
        return deleted


@dataclass
class SqlFinanceChatStore:
    """Persists the Financial Analyst chat history per worker -- previously in-memory only."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, message: FinanceChatMessage) -> FinanceChatMessage:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, message.tenant, message.agent_id)
            s.add(FinanceChatMessageRow(id=message.id, tenant_id=message.tenant, agent_id=message.agent_id,
                                        role=message.role, content=message.content,
                                        created_at=message.created_at))
        return message

    async def add_exchange(
        self, tenant: str, agent_id: str, user: FinanceChatMessage,
        assistant: FinanceChatMessage,
    ) -> None:
        async with self.sessionmaker() as session, session.begin():
            await _lock_enabled_agent(session, tenant, agent_id)
            session.add_all([
                FinanceChatMessageRow(
                    id=user.id, tenant_id=tenant, agent_id=agent_id,
                    role=user.role, content=user.content, created_at=user.created_at),
                FinanceChatMessageRow(
                    id=assistant.id, tenant_id=tenant, agent_id=agent_id,
                    role=assistant.role, content=assistant.content,
                    created_at=assistant.created_at),
            ])

    async def list_for_agent(self, tenant: str, agent_id: str,
                             limit: int | None = None) -> list[FinanceChatMessage]:
        async with self.sessionmaker() as s:
            q = select(FinanceChatMessageRow).where(
                FinanceChatMessageRow.tenant_id == tenant, FinanceChatMessageRow.agent_id == agent_id
            ).order_by(FinanceChatMessageRow.created_at)
            rows = (await s.execute(q)).scalars().all()
            items = [FinanceChatMessage(id=r.id, tenant=r.tenant_id, agent_id=r.agent_id, role=r.role,
                                        content=r.content, created_at=r.created_at) for r in rows]
            return items[-limit:] if limit else items

    async def clear(self, tenant: str, agent_id: str) -> int:
        async with self.sessionmaker() as s, s.begin():
            await _lock_enabled_agent(s, tenant, agent_id)
            result = await s.execute(delete(FinanceChatMessageRow).where(
                FinanceChatMessageRow.tenant_id == tenant, FinanceChatMessageRow.agent_id == agent_id))
            return result.rowcount or 0


# --- Notifications (app.modules.notifications) -----------------------------------------------
# Postgres-backed replacement for the in-memory notification store. Generic/reusable across
# verticals; every query is tenant-scoped and recipient-scoped (BOLA-safe): a row is visible when
# it is tenant-wide (user_id IS NULL) or addressed to the caller's own verified user_id.


def _notification_from_row(r: NotificationRow) -> Notification:
    return Notification(id=r.id, tenant=r.tenant_id, type=r.type, title=r.title, body=r.body,
                        category=r.category, user_id=r.user_id, agent_id=r.agent_id,
                        opportunity_id=r.opportunity_id, metadata=dict(r.metadata_json or {}),
                        read_at=r.read_at, created_at=r.created_at)


def _notification_visible(user_id: str | None):
    from sqlalchemy import or_

    return or_(NotificationRow.user_id.is_(None), NotificationRow.user_id == user_id)


@dataclass
class SqlNotificationStore:
    """Persists the generic in-app notification inbox -- previously in-memory only, so notifications
    were wiped on every redeploy. Shared by all verticals behind the NotificationStore protocol."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, notification: Notification) -> Notification:
        async with self.sessionmaker() as s, s.begin():
            if notification.agent_id:
                await _lock_enabled_agent(s, notification.tenant, notification.agent_id)
            s.add(NotificationRow(id=notification.id, tenant_id=notification.tenant, user_id=notification.user_id,
                                  category=notification.category, type=notification.type, title=notification.title,
                                  body=notification.body, agent_id=notification.agent_id,
                                  opportunity_id=notification.opportunity_id, metadata_json=notification.metadata,
                                  read_at=notification.read_at, created_at=notification.created_at))
        return notification

    async def get(self, tenant: str, notification_id: str) -> Notification | None:
        async with self.sessionmaker() as s:
            row = await s.get(NotificationRow, notification_id)
            return _notification_from_row(row) if row and row.tenant_id == tenant else None

    async def list_for_user(self, tenant: str, user_id: str | None, *, category: str | None = None,
                            unread_only: bool = False, limit: int | None = None) -> list[Notification]:
        async with self.sessionmaker() as s:
            q = select(NotificationRow).where(NotificationRow.tenant_id == tenant,
                                              _notification_visible(user_id))
            if category is not None:
                q = q.where(NotificationRow.category == category)
            if unread_only:
                q = q.where(NotificationRow.read_at.is_(None))
            q = q.order_by(NotificationRow.created_at.desc())
            if limit:
                q = q.limit(limit)
            rows = (await s.execute(q)).scalars().all()
            return [_notification_from_row(r) for r in rows]

    async def mark_read(self, tenant: str, notification_id: str, user_id: str | None) -> Notification | None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(NotificationRow, notification_id)
            if row is None or row.tenant_id != tenant or (row.user_id is not None and row.user_id != user_id):
                return None
            if row.read_at is None:
                row.read_at = datetime.now(timezone.utc)
            return _notification_from_row(row)

    async def mark_all_read(self, tenant: str, user_id: str | None, *, category: str | None = None) -> int:
        async with self.sessionmaker() as s, s.begin():
            q = select(NotificationRow).where(NotificationRow.tenant_id == tenant,
                                              _notification_visible(user_id), NotificationRow.read_at.is_(None))
            if category is not None:
                q = q.where(NotificationRow.category == category)
            rows = (await s.execute(q)).scalars().all()
            now = datetime.now(timezone.utc)
            for row in rows:
                row.read_at = now
            return len(rows)

    async def unread_count(self, tenant: str, user_id: str | None, *, category: str | None = None) -> int:
        return len(await self.list_for_user(tenant, user_id, category=category, unread_only=True))


def _aware(dt: datetime) -> datetime:
    """Coerce a datetime read back from the DB to timezone-aware UTC (SQLite drops tzinfo)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@dataclass
class SqlOtpStore:
    """Persists the password-reset OTP -- previously in-memory only, so a reset code stopped
    working on a redeploy and was never shared across processes. Only a keyed HMAC-SHA256 hash of
    the code is stored (never the plaintext), the row carries its own 10-minute expiry, and it is
    deleted on a successful verify so a code is strictly single-use."""
    sessionmaker: async_sessionmaker[AsyncSession]

    async def issue(self, email: str, *, ttl: int = 600) -> str:
        code = new_otp_code()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PasswordResetOtpRow, email.lower())
            if row is None:
                s.add(PasswordResetOtpRow(email=email.lower(), code_hash=hash_otp(code), expires_at=expires_at))
            else:
                # Re-issuing replaces any outstanding code for this email (only one is ever valid).
                row.code_hash = hash_otp(code)
                row.expires_at = expires_at
                row.created_at = datetime.now(timezone.utc)
        return code

    async def verify(self, email: str, otp: str) -> bool:
        async with self.sessionmaker() as s, s.begin():
            row = (await s.execute(
                select(PasswordResetOtpRow)
                .where(PasswordResetOtpRow.email == email.lower())
                .with_for_update()
            )).scalar_one_or_none()
            if row is None:
                return False
            if _aware(row.expires_at) < datetime.now(timezone.utc):
                await s.delete(row)  # prune the expired code
                return False
            if not secrets.compare_digest(row.code_hash, hash_otp(otp)):
                return False
            await s.delete(row)  # single-use: consume on success
            return True


@dataclass
class SqlPendingInviteStore:
    """Persists pending team invites (Creator Settings > Team tab) -- previously in-memory only,
    so an outstanding invite silently vanished on a redeploy. Fully tenant-scoped: every query is
    filtered by tenant_id, so a tenant can only ever read/write its own invites."""
    sessionmaker: async_sessionmaker[AsyncSession]

    @staticmethod
    def _to_invite(row: PendingTeamInviteRow) -> PendingInvite:
        return PendingInvite(email=row.email, role=Role(row.role), invited_at=_aware(row.invited_at).timestamp())

    async def list(self, tenant: str) -> list[PendingInvite]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(PendingTeamInviteRow).where(PendingTeamInviteRow.tenant_id == tenant)
                .order_by(PendingTeamInviteRow.invited_at))).scalars().all()
            return [self._to_invite(r) for r in rows]

    async def get(self, tenant: str, email: str) -> PendingInvite | None:
        async with self.sessionmaker() as s:
            row = await s.get(PendingTeamInviteRow, (tenant, email.lower()))
            return self._to_invite(row) if row is not None else None

    async def add(self, tenant: str, email: str, role: Role) -> PendingInvite:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PendingTeamInviteRow, (tenant, email.lower()))
            if row is None:
                row = PendingTeamInviteRow(tenant_id=tenant, email=email.lower(), role=role.value)
                s.add(row)
            else:
                row.role = role.value  # re-inviting updates the offered role, keeps invited_at
        return await self.get(tenant, email)

    async def remove(self, tenant: str, email: str) -> bool:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(PendingTeamInviteRow, (tenant, email.lower()))
            if row is None:
                return False
            await s.delete(row)
            return True


# --- Legal consent and pending signups -------------------------------------------------------


def _consent_from_row(row: ConsentRecordRow) -> ConsentRecord:
    return ConsentRecord(
        id=row.id,
        decision_id=row.decision_id,
        revision=row.revision,
        client_revision=row.client_revision,
        key_version=row.key_version,
        subject_hmac=row.subject_hmac,
        preferences=row.preferences,
        analytics=row.analytics,
        marketing=row.marketing,
        source=row.source,
        action=row.action,
        terms_release_id=row.terms_release_id,
        privacy_release_id=row.privacy_release_id,
        cookies_release_id=row.cookies_release_id,
        created_at=_aware(row.created_at),
    )


@dataclass
class SqlConsentStore:
    """Append-only consent store. Its public API deliberately has no mutation or deletion method."""

    sessionmaker: async_sessionmaker[AsyncSession]

    async def add(self, record: ConsentRecord) -> ConsentRecord:
        existing = await self.get(record.decision_id)
        if existing is not None:
            if not same_consent_decision(existing, record):
                raise ValueError("consent decision id conflict")
            return existing
        async with self.sessionmaker() as session, session.begin():
            session.add(ConsentRecordRow(
                id=record.id,
                decision_id=record.decision_id,
                revision=record.revision,
                client_revision=record.client_revision,
                key_version=record.key_version,
                subject_hmac=record.subject_hmac,
                preferences=record.preferences,
                analytics=record.analytics,
                marketing=record.marketing,
                source=record.source,
                action=record.action,
                terms_release_id=record.terms_release_id,
                privacy_release_id=record.privacy_release_id,
                cookies_release_id=record.cookies_release_id,
                created_at=record.created_at,
            ))
        return record

    async def get(self, decision_id: str) -> ConsentRecord | None:
        async with self.sessionmaker() as session:
            row = (await session.execute(select(ConsentRecordRow).where(
                ConsentRecordRow.decision_id == decision_id))).scalar_one_or_none()
            return _consent_from_row(row) if row is not None else None

    async def record_decision(
        self, *, subject_hmac: str, subject_hmacs: list[str], key_version: str,
        decision_id: str, client_revision: int, choices: ConsentChoices, source: ConsentSource,
        terms_release_id: str, privacy_release_id: str, cookies_release_id: str,
    ) -> ConsentRecord:
        async with self.sessionmaker() as session, session.begin():
            if session.bind.dialect.name == "postgresql":
                for lock_key in sorted({decision_id, *subject_hmacs}):
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": lock_key})
            existing_row = (await session.execute(select(ConsentRecordRow).where(
                ConsentRecordRow.decision_id == decision_id))).scalar_one_or_none()
            if existing_row is not None:
                existing = _consent_from_row(existing_row)
                same_request = (
                    existing.subject_hmac in subject_hmacs
                    and existing.client_revision == client_revision
                    and existing.preferences == choices.preferences
                    and existing.analytics == choices.analytics
                    and existing.marketing == choices.marketing
                    and existing.source == source
                    and existing.terms_release_id == terms_release_id
                    and existing.privacy_release_id == privacy_release_id
                    and existing.cookies_release_id == cookies_release_id
                )
                if not same_request:
                    raise ValueError("consent decision id conflict")
                return existing
            previous_row = (await session.execute(
                select(ConsentRecordRow)
                .where(ConsentRecordRow.subject_hmac.in_(subject_hmacs))
                .order_by(ConsentRecordRow.revision.desc())
                .limit(1)
            )).scalar_one_or_none()
            previous = _consent_from_row(previous_row) if previous_row is not None else None
            if previous is not None and client_revision < previous.client_revision:
                raise ValueError("stale consent decision")
            if previous is not None and client_revision == previous.client_revision:
                merged = ConsentChoices(
                    previous.preferences and choices.preferences,
                    previous.analytics and choices.analytics,
                    previous.marketing and choices.marketing)
                if (merged.preferences, merged.analytics, merged.marketing) == (
                        previous.preferences, previous.analytics, previous.marketing):
                    raise ValueError("stale consent decision")
                choices = merged
            revision = previous.revision + 1 if previous else 1
            action = "accept" if source == "signup" else derive_action(previous, choices)
            record = ConsentRecord(
                id=uuid.uuid4().hex, decision_id=decision_id, revision=revision,
                client_revision=client_revision, key_version=key_version, subject_hmac=subject_hmac,
                preferences=choices.preferences, analytics=choices.analytics,
                marketing=choices.marketing, source=source, action=action,
                terms_release_id=terms_release_id, privacy_release_id=privacy_release_id,
                cookies_release_id=cookies_release_id, created_at=datetime.now(timezone.utc))
            session.add(ConsentRecordRow(
                id=record.id, decision_id=record.decision_id, revision=record.revision,
                client_revision=record.client_revision, key_version=record.key_version, subject_hmac=record.subject_hmac,
                preferences=record.preferences, analytics=record.analytics,
                marketing=record.marketing, source=record.source, action=record.action,
                terms_release_id=record.terms_release_id,
                privacy_release_id=record.privacy_release_id,
                cookies_release_id=record.cookies_release_id, created_at=record.created_at))
            await session.flush()
            return record

    async def latest(self, subject_hmac: str) -> ConsentRecord | None:
        async with self.sessionmaker() as session:
            row = (await session.execute(
                select(ConsentRecordRow)
                .where(ConsentRecordRow.subject_hmac == subject_hmac)
                .order_by(ConsentRecordRow.revision.desc(), ConsentRecordRow.id.desc())
                .limit(1)
            )).scalar_one_or_none()
            return _consent_from_row(row) if row is not None else None

    async def list_policy_releases(self) -> list[PolicyRelease]:
        async with self.sessionmaker() as session:
            rows = (await session.execute(
                select(PolicyReleaseRow).order_by(PolicyReleaseRow.effective_at, PolicyReleaseRow.id)
            )).scalars().all()
            return [PolicyRelease(
                id=row.id,
                policy_type=row.policy_type,
                content_sha256=row.content_sha256,
                effective_at=_aware(row.effective_at),
            ) for row in rows]


@dataclass
class SqlPendingSignupStore:
    """Durable pending signup store with hashed, expiring, atomically consumed verification codes."""

    sessionmaker: async_sessionmaker[AsyncSession]

    @staticmethod
    def _to_domain(row: PendingSignupRow) -> PendingSignup:
        return PendingSignup(
            user_id=row.user_id,
            email=row.email,
            password_hash=row.password_hash,
            tenant=row.tenant_id,
            role=Role(row.role),
            code_hash=row.code_hash,
            expires_at=_aware(row.expires_at),
            terms_release_id=row.terms_release_id,
            privacy_release_id=row.privacy_release_id,
            cookies_release_id=row.cookies_release_id,
            invite_version=row.invite_version,
            attempts_remaining=row.attempts_remaining,
            completed_at=_aware(row.completed_at) if row.completed_at else None,
            completed_team_id=row.completed_team_id,
            created_at=_aware(row.created_at),
        )

    async def put(self, signup: PendingSignup) -> bool:
        async with self.sessionmaker() as session, session.begin():
            row = await session.get(PendingSignupRow, signup.email.lower())
            values = {
                "user_id": signup.user_id,
                "password_hash": signup.password_hash,
                "tenant_id": signup.tenant,
                "role": signup.role.value,
                "code_hash": signup.code_hash,
                "expires_at": signup.expires_at,
                "terms_release_id": signup.terms_release_id,
                "privacy_release_id": signup.privacy_release_id,
                "cookies_release_id": signup.cookies_release_id,
                "invite_version": signup.invite_version,
                "attempts_remaining": signup.attempts_remaining,
                "completed_at": signup.completed_at,
                "completed_team_id": signup.completed_team_id,
                "created_at": signup.created_at,
            }
            if row is not None and _aware(row.expires_at) > datetime.now(timezone.utc):
                return False
            if row is not None:
                await session.delete(row)
                await session.flush()
            session.add(PendingSignupRow(email=signup.email.lower(), **values))
            return True

    async def get(self, email: str) -> PendingSignup | None:
        async with self.sessionmaker() as session, session.begin():
            row = await session.get(PendingSignupRow, email.lower())
            if row is None:
                return None
            if _aware(row.expires_at) <= datetime.now(timezone.utc):
                await session.delete(row)
                return None
            return self._to_domain(row)

    async def consume(self, email: str, code: str) -> PendingSignup | None:
        async with self.sessionmaker() as session, session.begin():
            row = (await session.execute(
                select(PendingSignupRow)
                .where(PendingSignupRow.email == email.lower())
                .with_for_update()
            )).scalar_one_or_none()
            if row is None:
                return None
            if _aware(row.expires_at) <= datetime.now(timezone.utc):
                await session.delete(row)
                return None
            if not secrets.compare_digest(row.code_hash, hash_signup_code(code)):
                row.attempts_remaining -= 1
                if row.attempts_remaining <= 0:
                    await session.delete(row)
                return None
            return self._to_domain(row)

    async def finalize_signup(self, email: str, code: str, password_hash: str,
                              terms_release_id: str, privacy_release_id: str,
                              cookies_release_id: str) -> tuple[PendingSignup, bool] | None:
        async with self.sessionmaker() as session, session.begin():
            row = (await session.execute(
                select(PendingSignupRow).where(PendingSignupRow.email == email.lower()).with_for_update()
            )).scalar_one_or_none()
            if row is None:
                return None
            now = datetime.now(timezone.utc)
            if _aware(row.expires_at) <= now:
                await session.delete(row)
                return None
            if not secrets.compare_digest(row.code_hash, hash_signup_code(code)):
                row.attempts_remaining -= 1
                if row.attempts_remaining <= 0:
                    await session.delete(row)
                return None
            if row.completed_at is not None:
                return self._to_domain(row), False
            existing_user = (await session.execute(select(UserRow).where(UserRow.email == row.email))).scalar_one_or_none()
            if await session.get(UserRow, row.user_id) is not None or existing_user is not None:
                return None

            team_id = None
            if row.invite_version is None:
                if await session.get(TenantRow, row.tenant_id) is None:
                    session.add(TenantRow(id=row.tenant_id, name=row.tenant_id))
                team_id = uuid.uuid4().hex[:12]
                session.add(TeamRow(id=team_id, tenant_id=row.tenant_id))
                session.add(TeamMemberRow(team_id=team_id, user_id=row.email, role=Role.owner.value))
            else:
                invite = (await session.execute(
                    select(PendingTeamInviteRow)
                    .where(PendingTeamInviteRow.tenant_id == row.tenant_id,
                           PendingTeamInviteRow.email == row.email)
                    .with_for_update()
                )).scalar_one_or_none()
                if (invite is None or invite.role != row.role
                        or int(_aware(invite.invited_at).timestamp() * 1_000_000) != row.invite_version):
                    return None
                await session.delete(invite)

            accepted_at = datetime.now(timezone.utc)
            revision = int(accepted_at.timestamp() * 1000)
            key_version = active_pseudonym_version()
            session.add(ConsentRecordRow(
                id=uuid.uuid4().hex,
                decision_id=f"signup:{row.user_id}",
                revision=revision,
                client_revision=revision,
                key_version=key_version,
                subject_hmac=pseudonymous_subject("user", row.user_id, key_version),
                preferences=False,
                analytics=False,
                marketing=False,
                source="signup",
                action="accept",
                terms_release_id=terms_release_id,
                privacy_release_id=privacy_release_id,
                cookies_release_id=cookies_release_id,
                created_at=accepted_at,
            ))
            session.add(UserRow(
                id=row.user_id,
                email=row.email,
                password_hash=password_hash,
                tenant_id=row.tenant_id,
                role=row.role,
            ))
            row.completed_at = now
            row.completed_team_id = team_id
            row.expires_at = now + timedelta(minutes=10)
            await session.flush()
            return self._to_domain(row), True

    async def delete(self, email: str) -> None:
        async with self.sessionmaker() as session, session.begin():
            row = await session.get(PendingSignupRow, email.lower())
            if row is not None:
                await session.delete(row)

    async def purge_expired(self) -> int:
        async with self.sessionmaker() as session, session.begin():
            result = await session.execute(delete(PendingSignupRow).where(
                PendingSignupRow.expires_at <= datetime.now(timezone.utc)))
            return result.rowcount


@dataclass
class SqlUsageStore:
    """Durable AI usage accounting (QIK-514).

    Aggregation is done with SQL SUM grouped on columns that exist in both dialects. Day bucketing is
    done in Python from the raw rows in the window, because date_trunc is Postgres-only and much of
    the suite runs on SQLite: a portable-looking aggregate that silently returns nothing on one
    backend is worse than an explicit two-step.
    """

    sessionmaker: async_sessionmaker[AsyncSession]

    async def add_many(self, events: list[UsageEvent]) -> None:
        if not events:
            return
        async with self.sessionmaker() as s, s.begin():
            s.add_all([AiUsageEventRow(
                tenant_id=event.tenant, agent_id=event.agent_id, model_id=event.model_id,
                operation=event.operation, input_tokens=event.input_tokens,
                output_tokens=event.output_tokens, cost_nano_usd=event.cost_nano_usd,
                priced=event.priced, created_at=event.created_at) for event in events])

    def _window(self, tenant: str, start, end):
        query = select(AiUsageEventRow).where(AiUsageEventRow.tenant_id == tenant)
        if start is not None:
            query = query.where(AiUsageEventRow.created_at >= start)
        if end is not None:
            query = query.where(AiUsageEventRow.created_at <= end)
        return query

    async def _rows(self, tenant: str, start, end) -> list[UsageEvent]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(self._window(tenant, start, end))).scalars().all()
            return [UsageEvent(
                tenant=row.tenant_id, agent_id=row.agent_id, model_id=row.model_id,
                operation=row.operation, input_tokens=row.input_tokens,
                output_tokens=row.output_tokens, cost_nano_usd=row.cost_nano_usd,
                created_at=row.created_at, priced=row.priced) for row in rows]

    async def totals(self, tenant: str, *, start=None, end=None) -> UsageTotals:
        async with self.sessionmaker() as s:
            query = select(
                func.coalesce(func.sum(AiUsageEventRow.input_tokens), 0),
                func.coalesce(func.sum(AiUsageEventRow.output_tokens), 0),
                func.coalesce(func.sum(AiUsageEventRow.cost_nano_usd), 0),
                func.count(),
            ).where(AiUsageEventRow.tenant_id == tenant)
            if start is not None:
                query = query.where(AiUsageEventRow.created_at >= start)
            if end is not None:
                query = query.where(AiUsageEventRow.created_at <= end)
            row = (await s.execute(query)).one()
            unpriced = select(func.count()).where(
                AiUsageEventRow.tenant_id == tenant, AiUsageEventRow.priced.is_(False))
            if start is not None:
                unpriced = unpriced.where(AiUsageEventRow.created_at >= start)
            if end is not None:
                unpriced = unpriced.where(AiUsageEventRow.created_at <= end)
            return UsageTotals(input_tokens=int(row[0]), output_tokens=int(row[1]),
                               cost_nano_usd=int(row[2]), calls=int(row[3]),
                               unpriced_calls=int((await s.execute(unpriced)).scalar_one()))

    async def totals_by_agent(self, tenant: str, *, start=None, end=None) -> dict[str, UsageTotals]:
        return usage_group(await self._rows(tenant, start, end),
                           lambda event: event.agent_id or "unattributed")

    async def daily(self, tenant: str, *, start=None, end=None) -> dict[str, UsageTotals]:
        return usage_group(await self._rows(tenant, start, end),
                           lambda event: event.created_at.date().isoformat())

    async def _all_rows(self, start, end) -> list[UsageEvent]:
        # Cross-tenant: the platform AI-spend view ONLY.
        query = select(AiUsageEventRow)
        if start is not None:
            query = query.where(AiUsageEventRow.created_at >= start)
        if end is not None:
            query = query.where(AiUsageEventRow.created_at <= end)
        async with self.sessionmaker() as s:
            rows = (await s.execute(query)).scalars().all()
            return [UsageEvent(
                tenant=row.tenant_id, agent_id=row.agent_id, model_id=row.model_id,
                operation=row.operation, input_tokens=row.input_tokens,
                output_tokens=row.output_tokens, cost_nano_usd=row.cost_nano_usd,
                created_at=row.created_at, priced=row.priced) for row in rows]

    async def platform_totals(self, *, start=None, end=None) -> UsageTotals:
        # Cross-tenant. Aggregated in SQL rather than in Python: this is the one query that must stay
        # cheap as the table grows, because it is the headline number on the dashboard.
        async with self.sessionmaker() as s:
            query = select(
                func.coalesce(func.sum(AiUsageEventRow.input_tokens), 0),
                func.coalesce(func.sum(AiUsageEventRow.output_tokens), 0),
                func.coalesce(func.sum(AiUsageEventRow.cost_nano_usd), 0),
                func.count(),
            )
            unpriced = select(func.count()).where(AiUsageEventRow.priced.is_(False))
            if start is not None:
                query = query.where(AiUsageEventRow.created_at >= start)
                unpriced = unpriced.where(AiUsageEventRow.created_at >= start)
            if end is not None:
                query = query.where(AiUsageEventRow.created_at <= end)
                unpriced = unpriced.where(AiUsageEventRow.created_at <= end)
            row = (await s.execute(query)).one()
            return UsageTotals(input_tokens=int(row[0]), output_tokens=int(row[1]),
                               cost_nano_usd=int(row[2]), calls=int(row[3]),
                               unpriced_calls=int((await s.execute(unpriced)).scalar_one()))

    async def platform_by(self, dimension: str, *, start=None, end=None) -> dict[str, UsageTotals]:
        return usage_group(await self._all_rows(start, end), usage_dimensions()[dimension])

    async def platform_agent_usage(self, *, start=None, end=None) -> dict[str, AgentUsageSummary]:
        return summarise_agents(await self._all_rows(start, end))


@dataclass
class SqlCostCapStore:
    """Durable AI cost caps (QIK-522). Platform-wide, so no tenant filter by design."""

    sessionmaker: async_sessionmaker[AsyncSession]

    async def upsert(self, cap: CostCap) -> CostCap:
        async with self.sessionmaker() as s, s.begin():
            key = (cap.tenant, cap.agent_id or "")
            row = await s.get(AiCostCapRow, key)
            if row is None:
                s.add(AiCostCapRow(
                    tenant_id=cap.tenant, agent_id=cap.agent_id or "",
                    monthly_cap_nano_usd=cap.monthly_cap_nano_usd,
                    alert_threshold_pct=cap.alert_threshold_pct,
                    updated_by_email=cap.updated_by_email, updated_at=cap.updated_at))
            else:
                row.monthly_cap_nano_usd = cap.monthly_cap_nano_usd
                row.alert_threshold_pct = cap.alert_threshold_pct
                row.updated_by_email = cap.updated_by_email
                row.updated_at = cap.updated_at
            return cap

    async def delete(self, tenant: str, agent_id: str | None) -> None:
        async with self.sessionmaker() as s, s.begin():
            row = await s.get(AiCostCapRow, (tenant, agent_id or ""))
            if row is not None:
                await s.delete(row)

    async def list_all(self) -> list[CostCap]:
        async with self.sessionmaker() as s:
            rows = (await s.execute(select(AiCostCapRow).order_by(
                AiCostCapRow.tenant_id, AiCostCapRow.agent_id))).scalars().all()
            return [CostCap(tenant=row.tenant_id, agent_id=row.agent_id or None,
                            monthly_cap_nano_usd=row.monthly_cap_nano_usd,
                            alert_threshold_pct=row.alert_threshold_pct,
                            updated_by_email=row.updated_by_email,
                            updated_at=row.updated_at) for row in rows]


@dataclass
class SqlAuditStore:
    """The platform-wide audit trail. Cross-tenant by definition, so no tenant filter."""

    sessionmaker: async_sessionmaker[AsyncSession]
    # The synchronous sessionmaker the customer directory already uses. Passed in rather than built
    # per write, because the billing endpoints are plain `def` (they make blocking Stripe calls, so
    # making them async to suit the audit writer would move that block onto the event loop) and
    # building an engine per audit row would be a connection pool per event.
    sync_sessionmaker: object | None = None

    def add_in(self, session, row: dict) -> None:
        """Write inside the CALLER's transaction, for CRITICAL actions.

        Synchronous and takes the session, so the row is part of the same unit of work as the mutation
        it records. A committed mutation therefore cannot exist without its audit row, and a rolled
        back one cannot leave a row claiming it happened.
        """
        session.add(AuditEventRow(**row))

    async def add(self, row: dict) -> None:
        """Write afterwards, in its own transaction, for everything below CRITICAL."""
        async with self.sessionmaker() as s, s.begin():
            s.add(AuditEventRow(**row))

    def add_sync(self, row: dict) -> None:
        """Write from a synchronous handler.

        The billing endpoints are plain `def` and run in a threadpool, so they cannot await. They also
        make blocking HTTP calls to Stripe, which is exactly why they are not async: making them async
        to suit the audit writer would put that blocking call on the event loop.
        """
        if self.sync_sessionmaker is None:
            raise RuntimeError("no synchronous sessionmaker configured for the audit store")
        with self.sync_sessionmaker() as session, session.begin():
            session.add(AuditEventRow(**row))

    async def list(self, *, actions_to_hide: list[str] | None = None, action: str | None = None,
                   category: str | None = None, outcome: str | None = None,
                   tenant_id: str | None = None, actor_id: str | None = None,
                   target_id: str | None = None, request_id: str | None = None,
                   search: str | None = None, since=None, until=None,
                   cursor: tuple | None = None, limit: int = 100) -> list[dict]:
        query = select(AuditEventRow)
        # Applied in SQL, never after the LIMIT. Filtering a fetched page returns short pages with no
        # indication that more exist and, with a cursor, skips rows entirely.
        if actions_to_hide:
            query = query.where(AuditEventRow.action.notin_(actions_to_hide))
        for column, value in ((AuditEventRow.action, action), (AuditEventRow.category, category),
                              (AuditEventRow.outcome, outcome), (AuditEventRow.tenant_id, tenant_id),
                              (AuditEventRow.actor_id, actor_id), (AuditEventRow.target_id, target_id),
                              (AuditEventRow.request_id, request_id)):
            if value is not None:
                query = query.where(column == value)
        if since is not None:
            query = query.where(AuditEventRow.occurred_at >= since)
        if until is not None:
            query = query.where(AuditEventRow.occurred_at <= until)
        if search:
            # autoescape, because % and _ are wildcards and a TRAILING BACKSLASH is a Postgres error
            # rather than a no-match: an admin typing one would get a 500 from a search box.
            query = query.where(or_(
                func.lower(AuditEventRow.message).contains(search.lower(), autoescape=True),
                func.lower(func.coalesce(AuditEventRow.actor_label, "")).contains(
                    search.lower(), autoescape=True),
                func.lower(func.coalesce(AuditEventRow.target_label, "")).contains(
                    search.lower(), autoescape=True)))
        # Keyset paging. No OFFSET and no COUNT: both are what make an audit page unusable once the
        # table is large, and the total is not worth a full scan.
        #
        # The predicate compares the WHOLE sort key, not just the id. occurred_at is set when the event
        # happens while id is assigned at insert, and the non-transactional writer commits after the
        # mutation, so two concurrent requests routinely land with the two in opposite order. An
        # id-only cursor then skips rows outright, which for an audit page means some events are
        # invisible depending on where you happened to page.
        if cursor is not None:
            cursor_time, cursor_id = cursor
            query = query.where(or_(
                AuditEventRow.occurred_at < cursor_time,
                and_(AuditEventRow.occurred_at == cursor_time, AuditEventRow.id < cursor_id)))
        query = query.order_by(AuditEventRow.occurred_at.desc(), AuditEventRow.id.desc())

        async with self.sessionmaker() as s:
            # No clamp here: the caller asks for limit + 1 to detect a further page, and clamping it
            # back down made has_more permanently false at the maximum page size.
            rows = (await s.execute(query.limit(max(1, min(limit, 1000))))).scalars().all()
            return [_audit_json(row) for row in rows]


    async def rows_for_day(self, day) -> list[dict]:
        """Every row whose event time falls in one UTC day, for the archive export."""
        from app.modules.audit.archive import day_bounds

        start, end = day_bounds(day)
        async with self.sessionmaker() as s:
            rows = (await s.execute(
                select(AuditEventRow)
                .where(AuditEventRow.occurred_at >= start, AuditEventRow.occurred_at < end)
                .order_by(AuditEventRow.occurred_at, AuditEventRow.event_id))).scalars().all()
            return [_audit_json(row) for row in rows]

    async def apply_retention(self, now=None) -> dict:
        """Delete expired events and null expired network identifiers.

        Two separate cutoffs on purpose: the event is evidence and lives for 13 months, the address is
        an identifier attached to it and lives for 6. Nulling in place costs a field rather than an
        event, so the completeness the trail relies on is untouched.
        """
        from app.modules.audit.retention import DELETE_BATCH, cutoffs

        event_cutoff, network_cutoff = cutoffs(now)
        deleted = 0
        async with self.sessionmaker() as s:
            # Batched, because one unbounded DELETE over a large table holds a long lock and can time
            # out halfway, leaving an unpredictable amount done.
            while True:
                async with s.begin():
                    ids = (await s.execute(
                        select(AuditEventRow.id)
                        .where(AuditEventRow.occurred_at < event_cutoff)
                        .limit(DELETE_BATCH))).scalars().all()
                    if not ids:
                        break
                    await s.execute(delete(AuditEventRow).where(AuditEventRow.id.in_(ids)))
                    deleted += len(ids)
                if len(ids) < DELETE_BATCH:
                    break

            async with s.begin():
                cleared = (await s.execute(
                    update(AuditEventRow)
                    .where(AuditEventRow.occurred_at < network_cutoff,
                           or_(AuditEventRow.source_ip.is_not(None),
                               AuditEventRow.user_agent.is_not(None)))
                    .values(source_ip=None, user_agent=None))).rowcount or 0

        return {"events_deleted": deleted, "addresses_cleared": cleared,
                "cutoff_events": event_cutoff.isoformat(),
                "cutoff_network": network_cutoff.isoformat()}

    async def pseudonymise_subject(self, identifier: str, pseudonym: str, *,
                                   audit_row: Callable[[int], dict] | None = None) -> int:
        """Replace a subject's identifiers in place. Rows are never deleted for erasure.

        A gap in an audit trail is indistinguishable from tampering, so erasure replaces the identifying
        fields and leaves the timestamps, action, outcome and diffs exactly as they were. The row still
        proves that something happened, to whom under a stable pseudonym, and when.

        Matches on target and actor identifiers, not on the label alone: a subject can appear as the
        thing acted upon in one row and the actor in another, and an erasure that only handled one of
        those would leave the address behind in the other.
        """
        needle = identifier.strip().lower()
        matches = or_(func.lower(AuditEventRow.target_id) == needle,
                      func.lower(AuditEventRow.target_label) == needle,
                      func.lower(AuditEventRow.actor_id) == needle,
                      func.lower(AuditEventRow.actor_label) == needle)
        async with self.sessionmaker() as s, s.begin():
            if audit_row is not None:
                # Counted and recorded INSIDE the erasure's transaction. An erasure that lands without
                # its own record is the one case a regulator asks about directly, and unlike the other
                # CRITICAL actions no restructuring is needed: the erasure and its audit row live in
                # this store, so they share a unit of work. Counting here rather than passing a
                # prepared row is what lets the record carry the real number instead of omitting it.
                affected = (await s.execute(
                    select(func.count()).select_from(AuditEventRow).where(matches))).scalar() or 0
                s.add(AuditEventRow(**audit_row(affected)))
            result = await s.execute(
                update(AuditEventRow)
                .where(matches)
                .values(target_id=pseudonym, target_label=None, actor_id=pseudonym,
                        actor_label=None, source_ip=None, user_agent=None,
                        # The rendered sentence embeds the labels, so leaving it would have left the
                        # address in place in the one field a human actually reads. Replaced with the
                        # action rather than re-rendered: a pseudonym in a sentence reads as noise, and
                        # the structured columns already carry everything a reader needs.
                        message=AuditEventRow.action,
                        subject_pseudonym=pseudonym,
                        pseudonymised_at=datetime.now(timezone.utc)))
            return result.rowcount or 0


@dataclass
class SqlAuditArchiveStore:
    """The per-day digest ledger. Small, and read once per run."""

    sessionmaker: async_sessionmaker[AsyncSession]

    async def latest(self) -> dict | None:
        async with self.sessionmaker() as s:
            row = (await s.execute(
                select(AuditArchiveDigestRow)
                .order_by(AuditArchiveDigestRow.day.desc()).limit(1))).scalar_one_or_none()
            return None if row is None else {
                "day": row.day, "digest": row.digest, "row_count": row.row_count,
                "object_key": row.object_key}

    async def record(self, *, day: str, row_count: int, digest: str, previous_digest: str | None,
                     object_key: str) -> None:
        async with self.sessionmaker() as s, s.begin():
            existing = await s.get(AuditArchiveDigestRow, day)
            if existing is None:
                s.add(AuditArchiveDigestRow(
                    day=day, row_count=row_count, digest=digest, previous_digest=previous_digest,
                    object_key=object_key))
                return
            # Re-running a day overwrites rather than duplicating. A re-export of an unchanged day
            # produces an identical digest, so a CHANGED one on re-export is itself the tamper signal.
            existing.row_count = row_count
            existing.digest = digest
            existing.previous_digest = previous_digest
            existing.object_key = object_key
            existing.exported_at = datetime.now(timezone.utc)


def _worker_availability_row(*, tenant: str, agent_id: str, name: str | None,
                             changed_by_email: str, previous: bool, enabled: bool,
                             reason: str | None) -> dict:
    """Build the unified row for a worker availability change.

    Here rather than at the call site because the store is where the transaction is, and the whole point
    of folding these in was that the row shares that transaction. The actor is a platform admin: this
    path is only reachable from the admin console.
    """
    from app.modules.audit import registry as audit_actions
    from app.modules.audit import service as audit_service

    return audit_service.build_row(audit_service.AuditEvent(
        action=audit_actions.WORKER_ENABLED_CHANGED, target_id=agent_id, target_label=name,
        tenant_id=tenant, actor_type=audit_service.PLATFORM_ADMIN, actor_id=changed_by_email,
        actor_label=changed_by_email, reason=reason,
        changes=audit_service.diff(audit_actions.WORKER_ENABLED_CHANGED,
                                   {"enabled": previous}, {"enabled": enabled})))


def _platform_access_row(*, email: str, actor_email: str, previous_role: str | None, role: str | None,
                         previous_capabilities: list | None, capabilities: list | None,
                         reason: str | None) -> dict:
    """Build the unified row for a platform-access grant or revoke.

    The capability SETS are the substance, not just the role: the whole reason platform admins have
    capabilities is that "super_admin or nothing" was too blunt, so a row recording only the role would
    hide the change that actually happened most of the time.
    """
    from app.modules.audit import registry as audit_actions
    from app.modules.audit import service as audit_service

    revoked = role is None
    action = (audit_actions.PLATFORM_ACCESS_REVOKED if revoked
              else audit_actions.PLATFORM_ACCESS_GRANTED)
    return audit_service.build_row(audit_service.AuditEvent(
        action=action, target_id=email, target_label=email, actor_type=audit_service.PLATFORM_ADMIN,
        actor_id=actor_email, actor_label=actor_email, reason=reason,
        changes=audit_service.diff(action,
                                   {"role": previous_role, "capabilities": previous_capabilities},
                                   {"role": role, "capabilities": capabilities})))


def _audit_json(row: AuditEventRow) -> dict:
    """Fields listed explicitly, never the ORM object: the same rule every other admin read follows."""
    return {
        # The sequential id is deliberately NOT returned. A reader who is excluded from some actions
        # could otherwise count the gaps and learn exactly how many hidden events exist, which is the
        # disclosure the per-action read gate was preventing.
        "event_id": row.event_id, "action": row.action, "category": row.category,
        "outcome": row.outcome, "message": row.message,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "actor_type": row.actor_type, "actor_id": row.actor_id, "actor_label": row.actor_label,
        "on_behalf_of": row.on_behalf_of, "target_type": row.target_type, "target_id": row.target_id,
        "target_label": row.target_label, "tenant_id": row.tenant_id, "request_id": row.request_id,
        "source_ip": row.source_ip, "user_agent": row.user_agent, "route": row.route,
        "service": row.service, "environment": row.environment,
        "changes": dict(row.changes or {}), "metadata": dict(row.event_metadata or {}),
        "reason": row.reason,
        # Opaque to the client, and it carries the whole sort key so paging cannot skip.
        "_cursor": f"{row.occurred_at.isoformat()}|{row.id}",
    }
