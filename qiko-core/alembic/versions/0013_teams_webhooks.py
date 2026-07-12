"""teams_webhooks table (Microsoft Teams Integration, one webhook per tenant)

Revision ID: 0013_teams_webhooks
Revises: 0012_rfp_pack_outcome
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_teams_webhooks"
down_revision = "0012_rfp_pack_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams_webhooks",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("enc_webhook_url", sa.String(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("teams_webhooks")
