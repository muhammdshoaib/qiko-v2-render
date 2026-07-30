"""Add one-time MFA backup codes."""
from alembic import op
import sqlalchemy as sa

revision = "0027_mfa_backup_codes"
down_revision = "0026_encrypt_totp_secrets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mfa_backup_codes",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("selector", sa.String(length=4), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "selector"),
    )


def downgrade() -> None:
    op.drop_table("mfa_backup_codes")
