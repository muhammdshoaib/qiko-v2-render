"""rfp_pack_sections: per-section stepper reviewer columns

Adds two nullable columns to rfp_pack_sections so the RFP stepper flow
(Upload->Parsed->Assigned->Drafting->Review) can record a per-section REVIEWER: a tenant user id
(`reviewer`) plus a denormalised display name (`reviewer_name`) for easy render. Metadata only --
it does not gate whether/what answers are generated (drafts still run for every section). See
app.modules.rfp.tree.PackSection.

Revision ID: 0020_rfp_section_reviewer
Revises: 0019_rfp_pack_artifacts
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_rfp_section_reviewer"
down_revision = "0019_rfp_pack_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfp_pack_sections", sa.Column("reviewer", sa.String(64), nullable=True))
    op.add_column("rfp_pack_sections", sa.Column("reviewer_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("rfp_pack_sections", "reviewer_name")
    op.drop_column("rfp_pack_sections", "reviewer")
