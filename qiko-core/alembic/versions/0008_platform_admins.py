"""platform_admins table

Revision ID: 0008_platform_admins
Revises: 0007_assignments
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_platform_admins"
down_revision = "0007_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_admins",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("platform_admins")
