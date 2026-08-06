"""The platform-wide audit trail (admin overhaul, leg E1).

Six of 168 mutating endpoints were audited, and the six were almost all in one category. Money,
credentials, tenant access changes and deletions had no coverage at all: an operator could mark a
payment link paid, rotate a customer's Salesforce secret, delete every passage of a document or hard
delete a user, and nothing anywhere recorded that it happened or who did it.

One table rather than a fifth shape-specific one. The two older tables each model exactly one mutation,
which is why a third was added and a fourth was about to be. A single stream is also what the read UI,
retention, pseudonymisation and export each need to implement once.

Supersedes admin_action_audit, which is dropped here rather than kept: all three audit tables are
empty in production, so there is nothing to migrate and carrying a redundant table would leave two
places to look.
"""
from alembic import op
import sqlalchemy as sa

revision = "0037_audit_events"
down_revision = "0036_admin_action_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False, server_default="success"),
        sa.Column("message", sa.String(512), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False, server_default="system"),
        sa.Column("actor_id", sa.String(320), nullable=True),
        sa.Column("actor_label", sa.String(320), nullable=True),
        sa.Column("on_behalf_of", sa.String(64), nullable=True),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(320), nullable=True),
        sa.Column("target_label", sa.String(320), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("source_ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(256), nullable=True),
        sa.Column("route", sa.String(128), nullable=True),
        sa.Column("service", sa.String(32), nullable=False, server_default="api"),
        sa.Column("environment", sa.String(16), nullable=False, server_default="dev"),
        sa.Column("changes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("event_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("subject_pseudonym", sa.String(64), nullable=True),
        sa.Column("pseudonymised_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("event_id", "action", "category", "outcome", "occurred_at", "actor_type",
                   "actor_id", "target_id", "tenant_id", "request_id", "subject_pseudonym"):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])
    # Composite indexes for the read paths that matter: the chronological stream, and the same stream
    # narrowed to one tenant, one actor or one target.
    op.create_index("ix_audit_events_occurred_desc", "audit_events", ["occurred_at", "id"])
    op.create_index("ix_audit_events_tenant_time", "audit_events", ["tenant_id", "occurred_at"])
    op.create_index("ix_audit_events_actor_time", "audit_events", ["actor_id", "occurred_at"])
    op.create_index("ix_audit_events_target", "audit_events", ["target_type", "target_id"])

    op.drop_table("admin_action_audit")


def downgrade() -> None:
    op.create_table(
        "admin_action_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(320), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("actor_email", sa.String(320), nullable=False),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.drop_table("audit_events")
