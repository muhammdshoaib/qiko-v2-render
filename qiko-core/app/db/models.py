"""Domain ORM models. Every tenant-owned table carries tenant_id for central filtering.

Embeddings are stored as JSON so the schema is portable (SQLite in tests, Postgres in prod), and
SqlVectorStore does cosine ranking in Python. The pgvector extension is enabled (migration 0004);
moving the embedding column to a native `vector` type + HNSW index is a planned scale optimization,
not yet applied — the JSON path is the source of truth today.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, true
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
    user_id: Mapped[str] = mapped_column(String(64))
    agent_id: Mapped[str] = mapped_column(String(64))
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


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
    doc_id: Mapped[str] = mapped_column(String(128))
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
