"""Domain ORM models. Every tenant-owned table carries tenant_id for central filtering.

Embeddings are stored as JSON so the schema is portable (SQLite in tests, Postgres in prod), and
SqlVectorStore does cosine ranking in Python. The pgvector extension is enabled (migration 0004);
moving the embedding column to a native `vector` type + HNSW index is a planned scale optimization,
not yet applied — the JSON path is the source of truth today.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    twofa_enabled: Mapped[bool] = mapped_column(default=False)
    totp_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    current_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MfaBackupCode(Base):
    __tablename__ = "mfa_backup_codes"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    selector: Mapped[str] = mapped_column(String(4), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PolicyRelease(Base):
    """An immutable release of legal content, identified by its public release id and exact digest."""

    __tablename__ = "policy_releases"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_type: Mapped[str] = mapped_column(String(16))
    content_sha256: Mapped[str] = mapped_column(String(64))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (
        CheckConstraint("policy_type IN ('terms', 'privacy', 'cookies')", name="ck_policy_release_type"),
    )


class ConsentRecord(Base):
    """Append-only consent evidence. subject_hmac is pseudonymous and is not a User foreign key."""

    __tablename__ = "consent_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    revision: Mapped[int] = mapped_column(BigInteger, index=True)
    client_revision: Mapped[int] = mapped_column(BigInteger, index=True)
    key_version: Mapped[str] = mapped_column(String(16), default="v1")
    subject_hmac: Mapped[str] = mapped_column(String(64), index=True)
    preferences: Mapped[bool] = mapped_column(Boolean, nullable=False)
    analytics: Mapped[bool] = mapped_column(Boolean, nullable=False)
    marketing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16))
    terms_release_id: Mapped[str] = mapped_column(ForeignKey("policy_releases.id"))
    privacy_release_id: Mapped[str] = mapped_column(ForeignKey("policy_releases.id"))
    cookies_release_id: Mapped[str] = mapped_column(ForeignKey("policy_releases.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    __table_args__ = (
        CheckConstraint("source IN ('anonymous', 'authenticated', 'signup')", name="ck_consent_source"),
        CheckConstraint("action IN ('accept', 'reject', 'update', 'withdraw')", name="ck_consent_action"),
        Index("ix_consent_subject_created", "subject_hmac", "created_at"),
        Index("uq_consent_subject_revision", "subject_hmac", "revision", unique=True),
    )


class PendingSignup(Base):
    """A non-login-capable account candidate awaiting one-time email verification."""

    __tablename__ = "pending_signups"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    onboarding_worker: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts_remaining: Mapped[int] = mapped_column(default=5)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_team_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    terms_release_id: Mapped[str] = mapped_column(ForeignKey("policy_releases.id"))
    privacy_release_id: Mapped[str] = mapped_column(ForeignKey("policy_releases.id"))
    cookies_release_id: Mapped[str] = mapped_column(ForeignKey("policy_releases.id"))
    invite_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VerifiedAnswer(Base):
    __tablename__ = "verified_answers"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    topic: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_verified_tenant_topic", "tenant_id", "topic"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(320))
    agent_id: Mapped[str] = mapped_column(String(64))
    crm_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_conversation_tenant_user_agent", "tenant_id", "user_id", "agent_id"),)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    atype: Mapped[str] = mapped_column(String(32), default="worker")
    status: Mapped[str] = mapped_column(String(16), default="training")  # training -> ready
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())


class AgentStateAudit(Base):
    __tablename__ = "agent_state_audit"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    changed_by_email: Mapped[str] = mapped_column(String(320))
    previous_enabled: Mapped[bool]
    enabled: Mapped[bool]
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    __table_args__ = (Index("ix_agent_state_audit_tenant_agent_created", "tenant_id", "agent_id", "created_at"),)


class RfpPack(Base):
    __tablename__ = "rfp_packs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    client_name: Mapped[str] = mapped_column(String(255), default="")
    deadline: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(String(16), default="parsed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    document_text: Mapped[str] = mapped_column(String, default="")
    # Source document(s) the tender was parsed from -- one entry per successfully-read uploaded
    # file ({"name", "chars", "uploaded_at"}). Nullable JSON; read back as [] when unset.
    source_documents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Knowledge Base Reference (IDG-1000): when set, this job's answers are drafted ONLY from this
    # one knowledge base document, with no fallback to the wider corpus. NULL is the default and
    # means the full knowledge base, exactly as before. Set once at upload and never edited, so a
    # reviewer can always tell what a given draft was allowed to draw on. Width matches
    # Passage.doc_id, which is what it refers to.
    reference_doc_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Win/Loss Analysis (app.modules.rfp.service.OUTCOMES/LOSS_REASONS)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    outcome_reason: Mapped[str] = mapped_column(String(32), default="")
    outcome_value: Mapped[float | None] = mapped_column(nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Background tender-generation artifacts (persisted by the generate_tender_artifacts job) and
    # its pollable per-artifact progress (see app.modules.rfp.generation gen_status contract).
    brief: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    compliance: Mapped[list | None] = mapped_column(JSON, nullable=True)
    gen_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PackRequirement(Base):
    __tablename__ = "rfp_pack_requirements"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    pack_id: Mapped[str] = mapped_column(String(64), index=True)
    req_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    classification: Mapped[str] = mapped_column(String(16))
    requirement: Mapped[str] = mapped_column(String)


class PackSection(Base):
    """One section of an RFP pack's reviewer-facing tree (app.modules.rfp.tree). Sub-sections
    carry a parent_id; a section owns 1..n PackQuestions."""
    __tablename__ = "rfp_pack_sections"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    pack_id: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(512), default="")
    page: Mapped[int | None] = mapped_column(nullable=True)
    weighting: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="not_generated")
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_reviewer_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_reviewer_name: Mapped[str] = mapped_column(String(255), default="")
    # Stepper per-section reviewer (see app.modules.rfp.tree.PackSection) -- metadata only.
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manual: Mapped[bool] = mapped_column(default=False)
    kb_gap: Mapped[bool] = mapped_column(default=False)
    order_index: Mapped[int] = mapped_column(default=0)


class PackQuestion(Base):
    """One question under a PackSection (app.modules.rfp.tree). Carries the grounded AI draft plus
    the reviewer's editable/lockable user_draft; req_id links back to the flat PackRequirement so a
    locked user_draft can override the AI answer in exports."""
    __tablename__ = "rfp_pack_questions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    pack_id: Mapped[str] = mapped_column(String(64), index=True)
    section_id: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(String, default="")
    req_id: Mapped[str] = mapped_column(String(64), default="")
    word_limit: Mapped[int | None] = mapped_column(nullable=True)
    ai_answer: Mapped[str] = mapped_column(String, default="")
    ai_sources: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(default=0.0)  # writer's self-reported confidence
    grounding: Mapped[float] = mapped_column(default=0.0)   # independent critic grounding, distinct
    gaps: Mapped[str] = mapped_column(String, default="")   # writer's note of unsupported points
    decision: Mapped[str] = mapped_column(String(32), default="")
    kb_gap: Mapped[bool] = mapped_column(default=False)
    locked: Mapped[bool] = mapped_column(default=False)
    user_draft: Mapped[str] = mapped_column(String, default="")
    order_index: Mapped[int] = mapped_column(default=0)


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    pack_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64))
    rfp_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignee_user_id: Mapped[str] = mapped_column(String(64), index=True)
    assigned_by_user_id: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PlatformAdmin(Base):
    __tablename__ = "platform_admins"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    # NULL means "no explicit grant, use the role default". A list means exactly these capabilities,
    # so a viewer can be given one extra permission without being promoted to super_admin.
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AiUsageEvent(Base):
    """One model call, attributed to a tenant and (where known) a worker (QIK-514).

    Append-only. Deliberately NOT row-locked against the agents table like the sales-intelligence
    activity log is: a call that has already been billed by AWS must be recorded even if the worker
    was disabled a moment later, and several call sites have no worker at all.

    Cost is integer NANO-USD. Micro-USD rounded real calls to zero: Titan is 20 micro-USD per 1,000
    tokens, so an 8-token embedding cost 0.16 and disappeared, and an ingest embeds one chunk at a
    time. There is no Numeric or Float column anywhere in this schema and money is integer cents
    elsewhere; a float accumulating over millions of calls drifts.
    """

    __tablename__ = "ai_usage_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_id: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    # False when the model has no published rate in the price table, so unpriced spend is visible
    # rather than silently counted as free.
    priced: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    __table_args__ = (
        Index("ix_ai_usage_tenant_created", "tenant_id", "created_at"),
        Index("ix_ai_usage_tenant_agent_created", "tenant_id", "agent_id", "created_at"),
    )


class AiCostCap(Base):
    """An admin-set monthly AI spend cap (QIK-522).

    tenant_id "*" with a NULL agent_id is the platform-wide default. A worker row overrides its
    tenant row, which overrides the default. A cap of 0 blocks, and a NEGATIVE cap means explicitly
    unlimited: the alternative encoding (no row means unlimited) cannot distinguish "unlimited, and I
    meant it" from "nobody has configured this yet".
    """

    __tablename__ = "ai_cost_caps"
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Empty string rather than NULL, because a composite primary key cannot contain NULL.
    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True, default="")
    monthly_cap_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    alert_threshold_pct: Mapped[int] = mapped_column(default=80)
    updated_by_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEventRow(Base):
    """The platform-wide audit trail.

    One table, not a fifth shape-specific one. The two older tables each model exactly one mutation
    (agent_state_audit models `enabled`, platform_admin_audit models grants), which is why a third was
    added and then a fourth was about to be. A single stream is also what the read UI, retention,
    pseudonymisation and export each need to implement once rather than per table.

    No foreign keys, deliberately. An FK to users or agents would either block a deletion or
    cascade-delete the history of it, and the history of a deletion is the row that matters most.
    actor_label and target_label are snapshots taken at write time so a row still reads after the thing
    it refers to is gone or anonymised.

    Fields beyond the obvious exist because ISO 27002 8.15 names them as required log content and none
    of the previous tables had any: outcome, source address, user agent, and the identity of the
    service and environment that produced the event.
    """

    __tablename__ = "audit_events"
    # BigInteger, with an Integer variant for SQLite. SQLite only auto-increments a column declared
    # exactly INTEGER PRIMARY KEY, so a plain BigInteger key is NOT NULL with no default there and every
    # insert fails. Tests run on SQLite and production on Postgres, and this table had been in main for
    # several releases with no test ever inserting into it through the SQL store: every audit test used
    # the in-memory one, so the failure was invisible until a store-level test exercised the real path.
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"),
                                    primary_key=True, autoincrement=True)
    # Stable across environments and exports, so a row can be referenced or de-duplicated without
    # relying on an autoincrement that differs per database.
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    schema_version: Mapped[int] = mapped_column(default=1)

    action: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    outcome: Mapped[str] = mapped_column(String(16), default="success", index=True)
    # Rendered at write time so the sentence is fixed at the moment it happened, survives a later
    # rename, and makes a CSV export readable without the UI.
    message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Split on purpose: when it happened, and when we managed to write it down.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    actor_type: Mapped[str] = mapped_column(String(20), default="system", index=True)
    actor_id: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    actor_label: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Support access: the human who initiated is the actor, the impersonated party goes here.
    on_behalf_of: Mapped[str | None] = mapped_column(String(64), nullable=True)

    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    target_label: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # The tenant the event is ABOUT. NULL means platform scope; no "*" sentinel, because a sentinel in
    # an indexed filter column is a trap the cost-cap table already had to live with.
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Nulled after six months while the event itself is kept, which is the cheapest answer to a
    # minimisation challenge that does not cost an event. Enforced by the audit:apply_retention cron
    # job, not merely stated here: for one release this comment was the only thing that did it.
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    route: Mapped[str | None] = mapped_column(String(128), nullable=True)
    service: Mapped[str] = mapped_column(String(32), default="api")
    environment: Mapped[str] = mapped_column(String(16), default="dev")

    # Only the fields that changed, from a per-action allowlist. Never a snapshot: a snapshot copies
    # personal data into a second store and would carry encrypted credentials out of a worker config.
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set when an erasure request pseudonymises the row in place. Rows are never deleted for erasure:
    # gaps in an audit trail are indistinguishable from tampering.
    subject_pseudonym: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pseudonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_audit_events_occurred_desc", "occurred_at", "id"),
        Index("ix_audit_events_tenant_time", "tenant_id", "occurred_at"),
        Index("ix_audit_events_actor_time", "actor_id", "occurred_at"),
        Index("ix_audit_events_target", "target_type", "target_id"),
    )


class AuditArchiveDigest(Base):
    """One row per exported day: the digest, the row count, and the link to the previous day.

    Kept in the database as well as in the write-once object, deliberately. The copy in write-once storage
    is the one that matters for tamper evidence, because an attacker with database access can rewrite this
    one. This copy exists so the next run can chain onto it without a network round trip, and so an
    operator can see what has been exported without listing a bucket.
    """

    __tablename__ = "audit_archive_digests"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    row_count: Mapped[int] = mapped_column(default=0)
    digest: Mapped[str] = mapped_column(String(64))
    previous_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_key: Mapped[str] = mapped_column(String(255))
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PlatformAdminAudit(Base):
    """Append-only record of every platform-admin grant or revoke.

    Mirrors agent_state_audit: who changed whom, the before and after, an optional reason, and when.
    Platform admin is the highest privilege in the system and had no audit trail at all.
    """

    __tablename__ = "platform_admin_audit"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    changed_by_email: Mapped[str] = mapped_column(String(320))
    previous_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    previous_capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    __table_args__ = (Index("ix_platform_admin_audit_email_created", "email", "created_at"),)


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TeamMember(Base):
    __tablename__ = "team_members"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))


class Passage(Base):
    __tablename__ = "passages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    doc_id: Mapped[str] = mapped_column(String(128))
    # 0-based position within the document. See migration 0050 and knowledge.service._widen.
    ordinal: Mapped[int | None] = mapped_column(nullable=True)
    text: Mapped[str] = mapped_column(String)
    embedding: Mapped[list] = mapped_column(JSON, default=list)


class PackAnswer(Base):
    """Cached AI draft for one requirement in one RFP pack, so the cockpit's Sections tab doesn't
    re-run every LLM call (each one real network latency) on every page visit -- only on first
    view or an explicit regenerate."""
    __tablename__ = "rfp_pack_answers"
    pack_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    req_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    answer: Mapped[str] = mapped_column(String, default="")
    confidence: Mapped[float] = mapped_column(default=0.0)
    decision: Mapped[str] = mapped_column(String(32), default="")
    citations: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(String, default="")


class TeamsWebhook(Base):
    """One Microsoft Teams Incoming Webhook per tenant (app.modules.channels.teams_integration).
    The URL is encrypted at rest -- it grants posting rights into the customer's Teams channel."""
    __tablename__ = "teams_webhooks"
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enc_webhook_url: Mapped[str] = mapped_column(String)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Contact(Base):
    """A prospect who has talked to one of a tenant's workers -- the CRM/Sales Pipeline tab's
    real data source (app.modules.crm), replacing what was a client-side mock in the earlier
    qiko-frontend build. One contact per (agent, conversation): created lazily the first time a
    worker's pipeline is viewed, so no separate capture step is needed for the common case."""
    __tablename__ = "crm_contacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), default="Anonymous")
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="new")  # pipeline stage
    estimated_value: Mapped[int] = mapped_column(default=0)  # cents
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    ai_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    key_topics: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_crm_contact_tenant_agent", "tenant_id", "agent_id"),)


class CrmAction(Base):
    """A follow-up action suggested or logged against a CRM contact ("Next Actions" in the pipeline UI)."""
    __tablename__ = "crm_actions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    contact_id: Mapped[str] = mapped_column(ForeignKey("crm_contacts.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(32), default="custom")
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SalesIntelIngestionSource(Base):
    """UNGM/TED ingestion source config per worker (app.modules.sales_intelligence), ported from
    idg_sales_ingestion_sources."""
    __tablename__ = "sales_intel_ingestion_sources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    source_key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(40), default="portal")
    status: Mapped[str] = mapped_column(String(40), default="inactive")
    auth_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scan_cadence: Mapped[str] = mapped_column(String(80), default="manual")
    last_scan_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opportunities_found: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_sales_intel_source_agent", "tenant_id", "agent_id", "source_key", unique=True),)


class SalesIntelOpportunity(Base):
    """A UNGM/TED tender opportunity for one worker (app.modules.sales_intelligence), ported from
    idg_sales_opportunities."""
    __tablename__ = "sales_intel_opportunities"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    source_key: Mapped[str] = mapped_column(String(80))
    source_name: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str] = mapped_column(String(1024))
    buyer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_value: Mapped[float | None] = mapped_column(nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage: Mapped[str] = mapped_column(String(80), default="ingested")
    recommendation: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qualification_score: Mapped[int | None] = mapped_column(nullable=True)
    confidence: Mapped[int | None] = mapped_column(nullable=True)
    # Tracking half of a future calibration feedback loop: which verdict the IDG agentic
    # qualification pipeline (app.tasks.jobs.run_idg_qualification_pipeline) reached for this
    # opportunity, and which PipelineRun produced it. No auto-tuning reads these yet.
    pipeline_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    competitor_readiness: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qualification_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    qualification_reasons: Mapped[list] = mapped_column(JSON, default=list)
    qualification_dimensions: Mapped[dict] = mapped_column(JSON, default=dict)
    qualification_recommendations: Mapped[list] = mapped_column(JSON, default=list)
    rejection_reasons: Mapped[list] = mapped_column(JSON, default=list)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list)
    human_review_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    human_review_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_reviewer_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_reviewer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    salesforce_push_status: Mapped[str] = mapped_column(String(40), default="not_started")
    salesforce_opportunity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salesforce_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    salesforce_push_error: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (
        Index("ix_sales_intel_opp_source_external", "tenant_id", "agent_id", "source_key", "external_id", unique=True),
        Index("ix_sales_intel_opp_agent_stage", "tenant_id", "agent_id", "stage"),
    )


class SalesIntelActivityLog(Base):
    """Audit trail entry for one worker's sales-intelligence activity (source status, scan, or
    opportunity change), ported from idg_sales_activity_logs."""
    __tablename__ = "sales_intel_activity_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
    tone: Mapped[str] = mapped_column(String(40), default="info")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_sales_intel_log_agent_created", "tenant_id", "agent_id", "created_at"),)


class SalesIntelSalesforceConnection(Base):
    """One Salesforce OAuth connection (authorization_code + PKCE, with refresh) per worker,
    ported from idg_sales_salesforce_connections. Tokens are encrypted at rest via
    app.core.crypto -- see app.modules.sales_intelligence.salesforce."""
    __tablename__ = "sales_intel_salesforce_connections"
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), default="disconnected")
    instance_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enc_access_token: Mapped[str | None] = mapped_column(String, nullable=True)
    enc_refresh_token: Mapped[str | None] = mapped_column(String, nullable=True)
    token_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    salesforce_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salesforce_org_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connected_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SalesIntelIngestFilter(Base):
    """Persisted per-worker ingest filter (ported from idg_sales config.ingest_filters). One row
    per (tenant, agent): the portal keyword toggle + keyword, and the two allowlist-bypass flags
    (all_countries / all_categories). Applied to manual and scheduled scans when the request does
    not override them. Defaults mirror deployed Staging (query on, keyword 'security', bypass on)."""
    __tablename__ = "sales_intel_ingest_filters"
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    query_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    query_keyword: Mapped[str] = mapped_column(String(255), default="security")
    all_countries: Mapped[bool] = mapped_column(Boolean, default=True)
    all_categories: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    """A generic in-app notification for one tenant (app.modules.notifications), ported from the
    qiko-backend origin/idg-sales `notifications` table. Reusable across verticals (Sales
    Intelligence wires its triggers now; Pre-Sales will reuse the same table): `category` names
    the source module and `type` the event. `user_id` is optional -- NULL means tenant-wide
    (every user in the tenant sees it); a value scopes it to one recipient. `read_at` NULL == unread."""
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(64), default="general")
    type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String, default="")
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_notifications_tenant_user_created", "tenant_id", "user_id", "created_at"),)


class FinanceFile(Base):
    """One uploaded property-portfolio workbook + its parsed income/expense rows for a worker
    (app.modules.finance). The raw upload bytes are never stored -- only the normalized rows the
    analytics engine needs, as JSON, so the dashboard/chat can recompute without re-reading."""
    __tablename__ = "finance_files"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    source_name: Mapped[str] = mapped_column(String(255))
    namespace: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(default=0)
    row_count: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(8), default="GBP")
    expense_rows: Mapped[list] = mapped_column(JSON, default=list)
    income_rows: Mapped[list] = mapped_column(JSON, default=list)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_finance_files_agent", "tenant_id", "agent_id", "uploaded_at"),)


class FinanceChatMessage(Base):
    """One Financial Analyst chat turn for a worker (app.modules.finance)."""
    __tablename__ = "finance_chat_messages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_finance_chat_agent_created", "tenant_id", "agent_id", "created_at"),)


class SlackInstallation(Base):
    """One OAuth-installed Slack workspace (app.modules.channels.slack_oauth).

    Durable because the digest job runs on the arq worker tier, in a different process from the
    API that completed the OAuth flow: an in-memory installation store means the worker can never
    resolve a bot token, so the digest can never be posted. The bot token is stored already
    Fernet-encrypted by the service layer and is never written in plaintext.

    Keyed on (team_id, enterprise_id, tenant_id) so one workspace may legitimately be installed by
    more than one tenant, while the reverse lookup used by the Events API can detect that case and
    refuse to guess which tenant an inbound message belongs to.
    """
    __tablename__ = "slack_installations"
    team_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), primary_key=True, default="-")
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bot_token_encrypted: Mapped[str] = mapped_column(String(1024))
    bot_user_id: Mapped[str] = mapped_column(String(32))
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    installed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_slack_installations_workspace", "team_id", "enterprise_id"),)


class IntelligenceSignal(Base):
    """One normalised event from any source (app.modules.intelligence).

    The single table behind the Intelligence Worker. A Slack message, a merged PR, a Qiko Track
    transition, an uploaded document and a research finding are all rows here, which is what lets
    retrieval, chat, the digest and correlation each understand exactly one shape.

    `container` is WHERE it happened, source-defined: for Slack the workspace and channel, for
    GitHub the repository. It carries the workspace and not just the channel because a channel id
    is unique only within a workspace.

    `ref` is WHICH WORK ITEM it concerns, and it is the join key across sources. Most rows have
    none, and a row without one can only be reported as context, never as evidence.

    Unique on (tenant, agent, source, external_id): connectors re-read an overlapping window on
    every sweep, so the database enforces idempotency rather than trusting each connector to.
    """
    __tablename__ = "intelligence_signals"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(255))
    container: Mapped[str] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "source", "external_id",
                         name="uq_signal_identity"),
        # The read every consumer performs: one worker's signals in a window, newest first.
        Index("ix_signal_worker_time", "tenant_id", "agent_id", "occurred_at"),
        # Narrowed reads: the digest by container, correlation by ref.
        Index("ix_signal_container", "tenant_id", "agent_id", "container", "occurred_at"),
        Index("ix_signal_ref", "tenant_id", "agent_id", "ref"),
        # The retention sweep scans by age across every tenant.
        Index("ix_signal_occurred", "occurred_at"),
    )


class IntelligenceDocument(Base):
    """An uploaded document owned by a worker (app.modules.intelligence).

    The original bytes live in the storage backend; this row tracks status,
    metadata and the storage key so delete can remove both the object and the
    derived passages/signals.
    """
    __tablename__ = "intelligence_documents"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="uploading")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "doc_id", name="uq_intelligence_document"),
        Index("ix_intelligence_documents_worker", "tenant_id", "agent_id", "updated_at"),
    )


class IntelligencePipelineRun(Base):
    """A single orchestrated agentic pipeline run for the Intelligence Worker.

    Stages write their progress into `status` so a poller can observe the run without
    re-executing it. Cost and verdict are recorded when the magistrate stage finishes.
    """
    __tablename__ = "intelligence_pipeline_runs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    facets: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cost: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "run_id", name="uq_intelligence_pipeline_run"),
        Index("ix_intelligence_pipeline_runs_worker", "tenant_id", "agent_id", "updated_at"),
    )


class SlackChannelMessage(Base):
    """One captured Slack message for the AI heads-up assistant (app.modules.channels.slack_events)."""
    __tablename__ = "slack_channel_messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    team_id: Mapped[str] = mapped_column(String(32), index=True)
    # Part of the installation key, kept so the digest worker resolves the same workspace the
    # event arrived for. "-" is the non-enterprise sentinel, matching slack_installations.
    enterprise_id: Mapped[str] = mapped_column(String(32), default="-")
    channel_id: Mapped[str] = mapped_column(String(32), index=True)
    channel_type: Mapped[str] = mapped_column(String(16), default="channel")
    thread_ts: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_id: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    ts: Mapped[str] = mapped_column(String(32))
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (
        Index("ix_slack_msg_tenant_channel", "tenant_id", "channel_id"),
        Index("ix_slack_msg_team_ts", "team_id", "channel_id", "ts"),
        # The retention sweep scans by age across every tenant. Declared here rather than via
        # index=True on the column so the name matches migration 0040 exactly.
        Index("ix_slack_msg_created", "created_at"),
    )


class PasswordResetOtp(Base):
    """One outstanding password-reset code per email (app.modules.identity.onboarding).

    Previously in-memory only, so a reset code went dead on a redeploy and was never shared
    across processes. Only a keyed HASH of the six-digit code is stored (never the plaintext),
    the row carries its own expiry (10 minutes) and is deleted on a successful verify so a code
    is strictly single-use. Keyed by email, which is unique across the platform (users.email)."""
    __tablename__ = "password_reset_otps"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PendingTeamInvite(Base):
    """A person invited into a tenant who has not yet accepted (app.modules.identity.team_access).

    Previously in-memory only, so an outstanding invite silently vanished on a redeploy. Fully
    tenant-scoped (composite key tenant_id + email). Signed signup tokens are valid only while their
    exact pending role offer (including invitation version) remains current."""
    __tablename__ = "pending_team_invites"
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (Index("ix_pending_team_invites_tenant", "tenant_id"),)


class BillingSubscription(Base):
    """One subscription record (app.modules.billing.subscriptions.SubscriptionService).

    Previously in-memory only, so a tenant's plan/status was wiped on every restart. The primary
    key `subject` is the subscription subject exactly as the service keys it: the authenticated
    tenant for the tenant-scoped billing endpoints, or a team member's user id for the
    team-billing resolver. The Stripe subscription id + period are persisted for when a live
    Stripe key is wired (they stay NULL under the current stub gateway)."""
    __tablename__ = "billing_subscriptions"
    subject: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan: Mapped[str] = mapped_column(String(32), default="free")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | canceled
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BillingStripeCustomer(Base):
    """The real Stripe customer id ("cus_...") linked to a tenant, set from the checkout webhook
    (app.modules.billing.subscriptions.SubscriptionService.link_customer). Previously in-memory
    only, so the tenant<->Stripe-customer mapping was lost on restart."""
    __tablename__ = "billing_stripe_customers"
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stripe_customer_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BillingInvoice(Base):
    """A Stripe invoice synced by the webhook (app.modules.billing.webhook.InvoiceStore).

    Previously in-memory only, so synced invoices vanished on a restart and /billing/invoices
    came back empty after every redeploy. Idempotent by stripe_invoice_id (the webhook upserts)."""
    __tablename__ = "billing_invoices"
    stripe_invoice_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(255), index=True, default="")
    amount_cents: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_pdf: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BillingPaymentLink(Base):
    """An admin-created Stripe payment link and its logged lifecycle
    (app.modules.billing.payment_links.PaymentLinkService). Previously in-memory only, so the
    link log (and its paid/void status) was lost on a restart."""
    __tablename__ = "billing_payment_links"
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_email: Mapped[str] = mapped_column(String(320), index=True)
    amount_cents: Mapped[int] = mapped_column(default=0)
    url: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AdminCustomerFlag(Base):
    """Per-tenant admin overrides for the Customers console (app.modules.admin): the Studio-access
    toggle and the soft-delete flag. The customer directory itself is DERIVED from the real
    tenants/users/agents/subscriptions (SqlCustomerDirectory), so only these two admin-set flags
    need their own durable row -- everything else is computed from the source tables."""
    __tablename__ = "admin_customer_flags"
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_studio: Mapped[bool] = mapped_column(default=False)
    deleted: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class WebhookEvent(Base):
    """Durable idempotency key for inbound webhooks. Previously kept only in process memory,
    so duplicate deliveries across redeploys or replicas were not deduplicated."""
    __tablename__ = "webhook_events"
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InvestorActivityEvent(Base):
    """A single granular activity event synced directly from a client-side app (JM2-1131),
    keyed by tenant + investor_ref (opaque, whichever investor-facing backend minted the
    investor's activity token). category/label describe what happened (a screen visit, a
    property visit, a calculator step); property_name/location/postcode are the ONLY way a
    property may be identified here -- property_id/development_id/document_id/route params must
    never appear in this table, matching the client's activity-tracking identity rule."""
    __tablename__ = "investor_activity_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    investor_ref: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(255))
    property_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (
        Index("ix_investor_activity_tenant_investor", "tenant_id", "investor_ref"),
    )
