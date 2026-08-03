"""Add an editable display name to users (QIK-313 settings profile)."""
from alembic import op
import sqlalchemy as sa

revision = "0030_user_name"
down_revision = "0029_sales_intel_ingest_filters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "name")
