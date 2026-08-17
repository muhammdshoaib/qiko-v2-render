"""Intelligence Worker durable signal store.

A single table backs every source: Slack messages, GitHub activity, Qiko Track transitions,
uploaded documents and research findings. Normalising on one shape lets retrieval, the digest,
the chat layer and correlation each depend on exactly one model, and adding a source never
requires a second code path in any of them.

The unique constraint enforces idempotency at the database: connectors re-read overlapping
windows, so a duplicate external id per (tenant, worker, source) must fail rather than create
a second row.
"""
from alembic import op
import sqlalchemy as sa

revision = "0042_intelligence_signals"
down_revision = "0041_slack_channel_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_signals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), index=True, nullable=False),
        sa.Column("agent_id", sa.String(64), index=True, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("container", sa.String(255), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("ref", sa.String(64), nullable=True),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("flagged", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("meta", sa.JSON, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("tenant_id", "agent_id", "source", "external_id",
                            name="uq_signal_identity"),
    )
    op.create_index("ix_signal_worker_time", "intelligence_signals",
                    ["tenant_id", "agent_id", "occurred_at"])
    op.create_index("ix_signal_container", "intelligence_signals",
                    ["tenant_id", "agent_id", "container", "occurred_at"])
    op.create_index("ix_signal_ref", "intelligence_signals",
                    ["tenant_id", "agent_id", "ref"])
    op.create_index("ix_signal_occurred", "intelligence_signals", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_signal_occurred", table_name="intelligence_signals")
    op.drop_index("ix_signal_ref", table_name="intelligence_signals")
    op.drop_index("ix_signal_container", table_name="intelligence_signals")
    op.drop_index("ix_signal_worker_time", table_name="intelligence_signals")
    op.drop_table("intelligence_signals")
