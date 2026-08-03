"""Add per-worker scoping to knowledge passages (QIK-315).

Adds a nullable agent_id so a passage belongs to one worker; retrieval filters on it so a worker
never answers from another worker's knowledge. Nullable = existing rows stay tenant-wide until the
one-off backfill assigns them (or they are re-ingested per worker).
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_passage_agent_id"
down_revision = "0030_user_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("passages", sa.Column("agent_id", sa.String(length=64), nullable=True))
    op.create_index("ix_passages_agent_id", "passages", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_passages_agent_id", table_name="passages")
    op.drop_column("passages", "agent_id")
