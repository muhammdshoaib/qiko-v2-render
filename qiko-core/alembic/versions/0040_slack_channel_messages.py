"""Add slack_channel_messages table for the AI heads-up assistant.

Stores raw Slack messages captured from the Events API, tenant-scoped, so the
scheduled digest worker can read a recent window and generate a summary.
"""
from alembic import op
import sqlalchemy as sa

revision = "0040_slack_channel_messages"
down_revision = "0039_audit_append_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_channel_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), index=True, nullable=False),
        sa.Column("team_id", sa.String(32), index=True, nullable=False),
        sa.Column("channel_id", sa.String(32), index=True, nullable=False),
        sa.Column("channel_type", sa.String(16), default="channel", nullable=False),
        sa.Column("thread_ts", sa.String(32), nullable=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("ts", sa.String(32), nullable=False),
        sa.Column("flagged", sa.Boolean, default=False, nullable=False),
        sa.Column("tags", sa.JSON, default=list, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_slack_msg_tenant_channel", "slack_channel_messages", ["tenant_id", "channel_id"])
    op.create_index("ix_slack_msg_team_ts", "slack_channel_messages", ["team_id", "channel_id", "ts"])


def downgrade() -> None:
    op.drop_table("slack_channel_messages")
