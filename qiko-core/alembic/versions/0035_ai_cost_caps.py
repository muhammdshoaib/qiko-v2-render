"""Admin-set monthly AI cost caps (QIK-522).

Nothing limited AI spend. A single runaway tenant, or one worker in a retry loop against a tender
document, could accrue unbounded Bedrock charges with no ceiling and no alert, and the first signal
would have been the AWS bill.

agent_id is an empty string rather than NULL for the tenant-level and platform-level rows, because a
composite primary key cannot contain NULL and a partial unique index would behave differently on
SQLite, which much of the test suite runs on.
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_ai_cost_caps"
down_revision = "0034_ai_usage_nano_usd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_cost_caps",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), primary_key=True, server_default=""),
        sa.Column("monthly_cap_nano_usd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("alert_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("updated_by_email", sa.String(320), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_cost_caps")
