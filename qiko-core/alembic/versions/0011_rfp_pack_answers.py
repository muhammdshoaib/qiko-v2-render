"""rfp_pack_answers table (cached AI drafts per requirement)

Revision ID: 0011_rfp_pack_answers
Revises: 0010_leads_teams
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_rfp_pack_answers"
down_revision = "0010_leads_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rfp_pack_answers",
        sa.Column("pack_id", sa.String(64), primary_key=True),
        sa.Column("req_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("answer", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_rfp_pack_answers_tenant_id", "rfp_pack_answers", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_rfp_pack_answers_tenant_id", table_name="rfp_pack_answers")
    op.drop_table("rfp_pack_answers")
