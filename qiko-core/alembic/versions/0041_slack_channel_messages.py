"""Slack heads-up assistant: durable installations + the captured-message buffer.

Two tables, and both exist because of a durability boundary rather than a feature request.

`slack_installations` replaces an in-memory store. The digest job runs on the arq worker tier, in
a different process from the API that served the OAuth callback, so an in-process installation
store means the worker can never resolve a bot token: the digest is generated, billed, and then
has nowhere to go. The bot token is stored already Fernet-encrypted by the service layer.

`slack_channel_messages` buffers captured Slack text per (tenant, workspace, channel) so the
scheduled worker can read a bounded recent window. team_id is part of every read predicate on
purpose: a channel id is unique only WITHIN a workspace, so without it two workspaces sharing one
would be summarised as a single conversation.
"""
from alembic import op
import sqlalchemy as sa

revision = "0041_slack_channel_messages"
down_revision = "0040_conversation_crm_eligible"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_installations",
        # enterprise_id is part of the key and NOT nullable: a NULL would make the composite
        # primary key useless for the non-enterprise case, so "-" is the explicit sentinel.
        sa.Column("team_id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("enterprise_id", sa.String(32), primary_key=True, nullable=False,
                  server_default="-"),
        sa.Column("tenant_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("bot_token_encrypted", sa.String(1024), nullable=False),
        sa.Column("bot_user_id", sa.String(32), nullable=False),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("installed_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_slack_installations_workspace", "slack_installations",
                    ["team_id", "enterprise_id"])

    op.create_table(
        "slack_channel_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), index=True, nullable=False),
        sa.Column("team_id", sa.String(32), index=True, nullable=False),
        sa.Column("enterprise_id", sa.String(32), server_default="-", nullable=False),
        sa.Column("channel_id", sa.String(32), index=True, nullable=False),
        sa.Column("channel_type", sa.String(16), server_default="channel", nullable=False),
        sa.Column("thread_ts", sa.String(32), nullable=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("ts", sa.String(32), nullable=False),
        sa.Column("flagged", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_slack_msg_tenant_channel", "slack_channel_messages",
                    ["tenant_id", "channel_id"])
    # Covers the digest read, which filters on the workspace + channel and orders by ts.
    op.create_index("ix_slack_msg_team_ts", "slack_channel_messages",
                    ["team_id", "channel_id", "ts"])
    # Covers the retention sweep, which scans by age across every tenant.
    op.create_index("ix_slack_msg_created", "slack_channel_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("slack_channel_messages")
    op.drop_table("slack_installations")
