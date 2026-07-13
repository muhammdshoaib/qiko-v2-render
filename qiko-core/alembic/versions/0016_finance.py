"""finance_* tables (Finance vertical -- property-portfolio Excel ingestion, analytics and
Financial Analyst chat). Native replacement for the external excel-agent-server microservice.

Revision ID: 0016_finance
Revises: 0015_sales_intelligence
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_finance"
down_revision = "0015_sales_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_files",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="GBP"),
        sa.Column("expense_rows", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("income_rows", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_finance_files_agent", "finance_files", ["tenant_id", "agent_id", "uploaded_at"])

    op.create_table(
        "finance_chat_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_finance_chat_agent_created", "finance_chat_messages",
                    ["tenant_id", "agent_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_finance_chat_agent_created", table_name="finance_chat_messages")
    op.drop_table("finance_chat_messages")
    op.drop_index("ix_finance_files_agent", table_name="finance_files")
    op.drop_table("finance_files")
