"""Knowledge Base Reference: optional per-job reference document on an RFP pack (IDG-1000).

Additive and nullable. NULL means "the full knowledge base", which is the pre-existing behaviour,
so every pack that already exists keeps answering exactly as it did.
"""
import sqlalchemy as sa
from alembic import op

revision = "0047_rfp_reference_doc"
down_revision = "0046_intelligence_pipeline_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfp_packs", sa.Column("reference_doc_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("rfp_packs", "reference_doc_id")
