"""Intelligence Worker uploaded documents.

Tracks the storage key, status and metadata for documents uploaded to a worker.
The original bytes live in the storage backend; delete cascades to the object,
the passages and the signals derived from the document.
"""
from alembic import op
import sqlalchemy as sa

revision = "0043_intelligence_documents"
down_revision = "0042_intelligence_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_documents",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), index=True, nullable=False),
        sa.Column("agent_id", sa.String(64), index=True, nullable=False),
        sa.Column("doc_id", sa.String(64), index=True, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False, server_default="application/octet-stream"),
        sa.Column("size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="uploading"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("tenant_id", "agent_id", "doc_id", name="uq_intelligence_document"),
    )
    op.create_index("ix_intelligence_documents_worker", "intelligence_documents",
                    ["tenant_id", "agent_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_documents_worker", table_name="intelligence_documents")
    op.drop_table("intelligence_documents")
