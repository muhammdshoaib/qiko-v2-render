"""agents table

Revision ID: 0003_agents
Revises: 0002_conversations
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_agents"
down_revision = "0002_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("atype", sa.String(32), nullable=False, server_default="worker"),
        sa.Column("status", sa.String(16), nullable=False, server_default="training"),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_agents_tenant_id", "agents", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("agents")
