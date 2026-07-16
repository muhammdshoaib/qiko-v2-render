"""rfp_packs: persisted background-generation artifacts + status

Adds three nullable JSON columns to rfp_packs so uploading a tender can kick off a background job
that persists the Tender Brief, the Compliance checklist and a pollable per-artifact progress
(gen_status) -- see app.modules.rfp.generation. Requirements/sections/drafts already have their
own tables; these three fill the gaps that were previously on-demand and never persisted.

Revision ID: 0019_rfp_pack_artifacts
Revises: 0018_rfp_pack_tree
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_rfp_pack_artifacts"
down_revision = "0018_rfp_pack_tree"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfp_packs", sa.Column("brief", sa.JSON(), nullable=True))
    op.add_column("rfp_packs", sa.Column("compliance", sa.JSON(), nullable=True))
    op.add_column("rfp_packs", sa.Column("gen_status", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("rfp_packs", "gen_status")
    op.drop_column("rfp_packs", "compliance")
    op.drop_column("rfp_packs", "brief")
