"""assignments table

Revision ID: 0007_assignments
Revises: 0006_rfp_pack_requirements
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_assignments"
down_revision = "0006_rfp_pack_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("pack_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("rfp_title", sa.String(255), nullable=True),
        sa.Column("section_id", sa.String(64), nullable=True),
        sa.Column("section_title", sa.String(255), nullable=True),
        sa.Column("assignee_user_id", sa.String(64), nullable=False),
        sa.Column("assigned_by_user_id", sa.String(64), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_assignments_tenant_id", "assignments", ["tenant_id"])
    op.create_index("ix_assignments_pack_id", "assignments", ["pack_id"])
    op.create_index("ix_assignments_assignee_user_id", "assignments", ["assignee_user_id"])


def downgrade() -> None:
    op.drop_table("assignments")
