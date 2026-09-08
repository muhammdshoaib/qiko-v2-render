"""Investor activity events (JM2-1131).

Granular client-synced activity (screens, property visits, calculator steps), keyed by tenant +
investor_ref. Property identity is name/location/postcode only, never an id.
"""
from alembic import op
import sqlalchemy as sa

revision = "0049_investor_activity_events"
down_revision = "0048_passage_embedding_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investor_activity_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), index=True, nullable=False),
        sa.Column("investor_ref", sa.String(128), index=True, nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("property_name", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("postcode", sa.String(16), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_investor_activity_tenant_investor", "investor_activity_events",
                    ["tenant_id", "investor_ref"])


def downgrade() -> None:
    op.drop_index("ix_investor_activity_tenant_investor", table_name="investor_activity_events")
    op.drop_table("investor_activity_events")
