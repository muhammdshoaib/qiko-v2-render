"""rfp_packs table

Revision ID: 0005_rfp_packs
Revises: 0004_pgvector
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_rfp_packs"
down_revision = "0004_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rfp_packs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("client_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("deadline", sa.String(64), nullable=True),
        sa.Column("stage", sa.String(16), nullable=False, server_default="parsed"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_rfp_packs_tenant_id", "rfp_packs", ["tenant_id"])
    op.create_index("ix_rfp_packs_agent_id", "rfp_packs", ["agent_id"])


def downgrade() -> None:
    op.drop_table("rfp_packs")
