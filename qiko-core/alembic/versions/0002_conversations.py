"""conversations + messages

Revision ID: 0002_conversations
Revises: 0001_initial
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_conversations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversation_tenant_user_agent", "conversations",
                    ["tenant_id", "user_id", "agent_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(64), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
