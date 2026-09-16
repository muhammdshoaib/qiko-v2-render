"""add pipeline_attempt_count to opportunities: total-attempts cost-control gate for the agentic
qualification pipeline (OpportunityService._may_enqueue_pipeline).

The 0054 cooldown only bounds the RATE of enqueues for one opportunity, not the total: an
opportunity that never resolves (stays awaiting_review forever) still got a fresh agentic
pipeline run every time the cooldown elapsed, unbounded, so a tenant's Bedrock spend kept
climbing even with the cooldown in place (QIW cost incident continuation, 2026-09-16 - Ali
flagged a fresh anomaly in #leadership two days after the 0054 fix shipped). This column lets
the gate stop retrying a given opportunity after idg_pipeline_max_attempts, independent of how
much time has passed.

Revision ID: 0055_pipeline_attempt_count
Revises: 0054_pipeline_enqueue_cooldown
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0055_pipeline_attempt_count"
down_revision = "0054_pipeline_enqueue_cooldown"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales_intel_opportunities",
                  sa.Column("pipeline_attempt_count", sa.Integer(), nullable=False,
                            server_default="0"))


def downgrade() -> None:
    op.drop_column("sales_intel_opportunities", "pipeline_attempt_count")
