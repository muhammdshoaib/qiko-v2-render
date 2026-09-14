"""add pipeline_last_enqueued_at to opportunities: enqueue-cooldown marker for the agentic
qualification pipeline's cost-control gate (OpportunityService._may_enqueue_pipeline).

Set the moment a pipeline run is enqueued for an opportunity, not on completion (unlike the
existing pipeline_verdict/pipeline_run_id columns from 0051): _scan_source() previously
re-enqueued a full Synthesizer/Critic pipeline run for any opportunity still awaiting_review on
every single scan cycle, with no de-dup at all (QIW cost incident, 2026-09-14 - see
.devin/ledger/idg-pipeline-cost-fix-20260914.md). This column lets the gate skip an opportunity
that already has a recent-or-in-flight run without needing to correlate against PipelineRun rows,
which carry no opportunity_id.

Revision ID: 0054_pipeline_enqueue_cooldown
Revises: 0053_jm_intent_signals
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0054_pipeline_enqueue_cooldown"
down_revision = "0053_jm_intent_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales_intel_opportunities",
                  sa.Column("pipeline_last_enqueued_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_intel_opportunities", "pipeline_last_enqueued_at")
