"""add pipeline_verdict/pipeline_run_id to opportunities: tracking half of a calibration feedback
loop (see .devin/specs/2026-09-08-orchestration-quality-cost-efficiency-design.md) - every notice
that went through the IDG agentic qualification pipeline now carries which verdict it got,
joinable against the deterministic scorer's own recommendation/qualification_score columns
already on the same row. No auto-tuning added in this migration or this phase - tracking only.

Revision ID: 0051_pipeline_verdict
Revises: 0050_passage_ordinal
Create Date: 2026-09-08

Note: alembic_version.version_num is varchar(32) (alembic's own default schema, unchanged by
this codebase). The original revision id ("0051_opportunity_pipeline_verdict", 33 chars) exceeded
that and broke `alembic upgrade head` in production with a StringDataRightTruncation error that
none of the local/CI migration tests (SQLite-backed, which does not enforce VARCHAR length)
caught. Renamed to fit under the real limit.
"""
from alembic import op
import sqlalchemy as sa

revision = "0051_pipeline_verdict"
down_revision = "0050_passage_ordinal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales_intel_opportunities",
                  sa.Column("pipeline_verdict", sa.String(length=16), nullable=True))
    op.add_column("sales_intel_opportunities",
                  sa.Column("pipeline_run_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_intel_opportunities", "pipeline_run_id")
    op.drop_column("sales_intel_opportunities", "pipeline_verdict")
