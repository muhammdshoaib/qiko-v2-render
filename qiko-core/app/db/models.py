"""Domain ORM models. Every tenant-owned table carries tenant_id for central filtering.

Embeddings are stored as JSON so the schema is portable (SQLite in tests, Postgres in prod), and
SqlVectorStore does cosine ranking in Python. The pgvector extension is enabled (migration 0004);
moving the embedding column to a native `vector` type + HNSW index is a planned scale optimization,
not yet applied — the JSON path is the source of truth today.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
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
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    # Win/Loss Analysis (app.modules.rfp.service.OUTCOMES/LOSS_REASONS)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    outcome_reason: Mapped[str] = mapped_column(String(32), default="")
    outcome_value: Mapped[float | None] = mapped_column(nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PackRequirement(Base):
    __tablename__ = "rfp_pack_requirements"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    pack_id: Mapped[str] = mapped_column(String(64), index=True)
    req_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    classification: Mapped[str] = mapped_column(String(16))
    requirement: Mapped[str] = mapped_column(String)


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
