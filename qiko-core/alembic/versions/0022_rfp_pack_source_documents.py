"""rfp_packs.source_documents column

Adds a nullable JSON column to rfp_packs recording WHICH file(s) a tender was parsed from -- one
entry per successfully-read upload ({"name", "chars", "uploaded_at"}). Persisted separately from
document_text/gen_status so the cockpit can always show the source document set, including after a
re-extract resets gen_status. See app.modules.rfp.service.RfpPack.source_documents.

Revision ID: 0022_rfp_pack_source_documents
Revises: 0021_rfp_question_grounding_gaps
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_rfp_pack_source_documents"
down_revision = "0021_rfp_question_grounding_gaps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfp_packs", sa.Column("source_documents", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("rfp_packs", "source_documents")
