"""password_reset_otps + pending_team_invites tables

Makes the password-reset OTP store and the pending team-invite store durable (Postgres-backed),
so a reset code or an outstanding invite survives a redeploy and is shared across processes.

Revision ID: 0023_otp_and_pending_invites
Revises: 0022_rfp_pack_source_documents
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_otp_and_pending_invites"
down_revision = "0022_rfp_pack_source_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_otps",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "pending_team_invites",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pending_team_invites_tenant", "pending_team_invites", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_pending_team_invites_tenant", table_name="pending_team_invites")
    op.drop_table("pending_team_invites")
    op.drop_table("password_reset_otps")
