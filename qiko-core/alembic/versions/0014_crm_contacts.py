"""crm_contacts + crm_actions tables (real CRM/Sales Pipeline data, replacing the earlier
qiko-frontend client-side mock)

Revision ID: 0014_crm_contacts
Revises: 0013_teams_webhooks
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_crm_contacts"
down_revision = "0013_teams_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_contacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False, server_default="Anonymous"),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("estimated_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("ai_summary", sa.String(), nullable=True),
        sa.Column("sentiment", sa.String(16), nullable=True),
        sa.Column("key_topics", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crm_contact_tenant_agent", "crm_contacts", ["tenant_id", "agent_id"])

    op.create_table(
        "crm_actions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("contact_id", sa.String(64), sa.ForeignKey("crm_contacts.id"), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False, server_default="custom"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crm_actions_contact", "crm_actions", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_crm_actions_contact", table_name="crm_actions")
    op.drop_table("crm_actions")
    op.drop_index("ix_crm_contact_tenant_agent", table_name="crm_contacts")
    op.drop_table("crm_contacts")
