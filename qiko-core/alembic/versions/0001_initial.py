"""initial schema: tenants, users, verified_answers, passages

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-04

On Postgres the passages.embedding column is migrated to a pgvector `vector` type with an HNSW
index for scale (applied in a follow-up PG-only migration); the portable JSON column here works
for SQLite/dev and small volumes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
        sa.Column("twofa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("totp_secret", sa.String(64), nullable=True),
        sa.Column("current_sid", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_table(
        "verified_answers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_verified_tenant_topic", "verified_answers", ["tenant_id", "topic"])
    op.create_table(
        "passages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("doc_id", sa.String(128), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_passages_tenant_id", "passages", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("passages")
    op.drop_table("verified_answers")
    op.drop_table("users")
    op.drop_table("tenants")
