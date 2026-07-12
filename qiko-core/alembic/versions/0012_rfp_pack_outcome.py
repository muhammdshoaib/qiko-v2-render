"""rfp_packs win/loss outcome columns

Revision ID: 0012_rfp_pack_outcome
Revises: 0011_rfp_pack_answers
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_rfp_pack_outcome"
down_revision = "0011_rfp_pack_answers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfp_packs", sa.Column("outcome", sa.String(16), nullable=True))
    op.add_column("rfp_packs", sa.Column("outcome_reason", sa.String(32), nullable=False, server_default=""))
    op.add_column("rfp_packs", sa.Column("outcome_value", sa.Float(), nullable=True))
    op.add_column("rfp_packs", sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("rfp_packs", "outcome_at")
    op.drop_column("rfp_packs", "outcome_value")
    op.drop_column("rfp_packs", "outcome_reason")
    op.drop_column("rfp_packs", "outcome")
