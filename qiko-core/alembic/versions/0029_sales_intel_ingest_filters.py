"""Add per-worker persisted Sales Intelligence ingest filter settings."""
from alembic import op
import sqlalchemy as sa

revision = "0029_sales_intel_ingest_filters"
down_revision = "0028_consent_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales_intel_ingest_filters",
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("query_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("query_keyword", sa.String(length=255), nullable=False, server_default="security"),
        sa.Column("all_countries", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("all_categories", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "agent_id"),
    )


def downgrade() -> None:
    op.drop_table("sales_intel_ingest_filters")
