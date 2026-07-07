"""rfp_pack_requirements table

Revision ID: 0006_rfp_pack_requirements
Revises: 0005_rfp_packs
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_rfp_pack_requirements"
down_revision = "0005_rfp_packs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rfp_pack_requirements",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("pack_id", sa.String(64), nullable=False),
        sa.Column("req_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("requirement", sa.String(), nullable=False),
    )
    op.create_index("ix_rfp_pack_requirements_tenant_id", "rfp_pack_requirements", ["tenant_id"])
    op.create_index("ix_rfp_pack_requirements_pack_id", "rfp_pack_requirements", ["pack_id"])


def downgrade() -> None:
    op.drop_table("rfp_pack_requirements")
