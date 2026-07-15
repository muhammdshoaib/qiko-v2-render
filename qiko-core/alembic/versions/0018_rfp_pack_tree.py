"""rfp_pack_sections + rfp_pack_questions tables (the reviewer-facing section->question tree)

Adds the validated tender-cockpit model on top of the flat rfp_pack_requirements list: a pack owns
sections, each section owns questions with per-question lock/draft/word-limit and section-level
reviewer/weighting/manual/kb-gap. See app.modules.rfp.tree.

Revision ID: 0018_rfp_pack_tree
Revises: 0017_notifications_and_reviewer
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_rfp_pack_tree"
down_revision = "0017_notifications_and_reviewer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rfp_pack_sections",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("pack_id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, server_default=""),
        sa.Column("name", sa.String(512), nullable=False, server_default=""),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("weighting", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_generated"),
        sa.Column("parent_id", sa.String(64), nullable=True),
        sa.Column("assigned_reviewer_user_id", sa.String(64), nullable=True),
        sa.Column("assigned_reviewer_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("due_date", sa.String(64), nullable=True),
        sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kb_gap", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_rfp_pack_sections_tenant_id", "rfp_pack_sections", ["tenant_id"])
    op.create_index("ix_rfp_pack_sections_pack_id", "rfp_pack_sections", ["pack_id"])

    op.create_table(
        "rfp_pack_questions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("pack_id", sa.String(64), nullable=False),
        sa.Column("section_id", sa.String(64), nullable=False),
        sa.Column("text", sa.String(), nullable=False, server_default=""),
        sa.Column("req_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("word_limit", sa.Integer(), nullable=True),
        sa.Column("ai_answer", sa.String(), nullable=False, server_default=""),
        sa.Column("ai_sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("decision", sa.String(32), nullable=False, server_default=""),
        sa.Column("kb_gap", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_draft", sa.String(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_rfp_pack_questions_tenant_id", "rfp_pack_questions", ["tenant_id"])
    op.create_index("ix_rfp_pack_questions_pack_id", "rfp_pack_questions", ["pack_id"])
    op.create_index("ix_rfp_pack_questions_section_id", "rfp_pack_questions", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_rfp_pack_questions_section_id", table_name="rfp_pack_questions")
    op.drop_index("ix_rfp_pack_questions_pack_id", table_name="rfp_pack_questions")
    op.drop_index("ix_rfp_pack_questions_tenant_id", table_name="rfp_pack_questions")
    op.drop_table("rfp_pack_questions")
    op.drop_index("ix_rfp_pack_sections_pack_id", table_name="rfp_pack_sections")
    op.drop_index("ix_rfp_pack_sections_tenant_id", table_name="rfp_pack_sections")
    op.drop_table("rfp_pack_sections")
