"""rfp_packs.document_text column

Revision ID: 0009_rfp_pack_document_text
Revises: 0008_platform_admins
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_rfp_pack_document_text"
down_revision = "0008_platform_admins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfp_packs", sa.Column("document_text", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("rfp_packs", "document_text")
