"""rfp_pack_questions: distinct grounding + gaps columns

Adds two columns to rfp_pack_questions so a drafted question can carry the independent critic's
GROUNDING score and the writer's GAPS note SEPARATELY from `confidence` (the writer's self-reported
confidence). Previously confidence and grounding were the same number; they are now distinct. See
app.modules.rfp.tree.PackQuestion / app.modules.agentcore.

Revision ID: 0021_rfp_question_grounding_gaps
Revises: 0020_rfp_section_reviewer
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_rfp_question_grounding_gaps"
down_revision = "0020_rfp_section_reviewer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfp_pack_questions",
                  sa.Column("grounding", sa.Float(), nullable=False, server_default="0"))
    op.add_column("rfp_pack_questions",
                  sa.Column("gaps", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("rfp_pack_questions", "gaps")
    op.drop_column("rfp_pack_questions", "grounding")
