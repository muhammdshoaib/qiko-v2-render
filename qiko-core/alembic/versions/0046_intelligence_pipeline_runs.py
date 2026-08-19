"""Intelligence Worker orchestration pipeline runs.

Tracks the status, verdict and per-stage cost of a single pipeline run.
The actual stage outputs are part of the run record and live in the JSON status field.
"""
from alembic import op
import sqlalchemy as sa

revision = "0046_intelligence_pipeline_runs"
down_revision = "0045_billing_invoices_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_pipeline_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), index=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), index=True, nullable=False),
        sa.Column("agent_id", sa.String(64), index=True, nullable=False),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("facets", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.JSON, nullable=True),
        sa.Column("verdict", sa.String(16), nullable=True),
        sa.Column("cost", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("tenant_id", "agent_id", "run_id",
                            name="uq_intelligence_pipeline_run"),
    )
    op.create_index("ix_intelligence_pipeline_runs_worker",
                    "intelligence_pipeline_runs",
                    ["tenant_id", "agent_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_pipeline_runs_worker",
                  table_name="intelligence_pipeline_runs")
    op.drop_table("intelligence_pipeline_runs")
