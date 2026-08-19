"""Durable webhook event idempotency.

The in-memory IdempotencyGuard lost deduplication state on every redeploy and could not
share state across replicas. A composite primary key on (source, event_id) makes duplicate
delivery safe across processes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0044_webhook_idempotency"
down_revision = "0043_intelligence_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("source", "event_id"),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
