"""Generic in-app notifications table + reviewer-assignment columns on sales_intel_opportunities.

Ports two non-AI Sales-Intelligence features from the unmerged qiko-backend origin/idg-sales
Laravel branch:
 - the generic `notifications` table (from create_idg_sales_notifications + the migrate-to-generic
   `notifications` migration) -- reusable across verticals, SI wires its triggers now;
 - the assign-reviewer columns (assigned_reviewer_user_id / assigned_by_user_id / assigned_at,
   plus a V2 assigned_reviewer_name free-text fallback) on sales_intel_opportunities.

Revision ID: 0017_notifications_and_reviewer
Revises: 0016_finance
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_notifications_and_reviewer"
down_revision = "0016_finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=False, server_default="general"),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.String(), nullable=False, server_default=""),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("opportunity_id", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_agent_id", "notifications", ["agent_id"])
    op.create_index("ix_notifications_tenant_user_created", "notifications",
                    ["tenant_id", "user_id", "created_at"])

    op.add_column("sales_intel_opportunities",
                  sa.Column("assigned_reviewer_user_id", sa.String(64), nullable=True))
    op.add_column("sales_intel_opportunities",
                  sa.Column("assigned_reviewer_name", sa.String(255), nullable=True))
    op.add_column("sales_intel_opportunities",
                  sa.Column("assigned_by_user_id", sa.String(64), nullable=True))
    op.add_column("sales_intel_opportunities",
                  sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_intel_opportunities", "assigned_at")
    op.drop_column("sales_intel_opportunities", "assigned_by_user_id")
    op.drop_column("sales_intel_opportunities", "assigned_reviewer_name")
    op.drop_column("sales_intel_opportunities", "assigned_reviewer_user_id")
    op.drop_index("ix_notifications_tenant_user_created", table_name="notifications")
    op.drop_index("ix_notifications_agent_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_tenant_id", table_name="notifications")
    op.drop_table("notifications")
