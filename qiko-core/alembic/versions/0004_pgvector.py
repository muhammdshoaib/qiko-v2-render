"""enable pgvector (Postgres only)

Revision ID: 0004_pgvector
Revises: 0003_agents
Create Date: 2026-07-04

Enables the pgvector extension on Postgres so passage embeddings can move from the portable JSON
column to a native `vector` column with an HNSW index at scale. No-op on SQLite (dev/tests), where
embeddings stay JSON and cosine is computed in Python.
"""
from alembic import op

revision = "0004_pgvector"
down_revision = "0003_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    pass
