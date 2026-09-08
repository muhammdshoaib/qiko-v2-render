"""add native pgvector column + HNSW index to passages (Postgres only)

Revision ID: 0048_passage_embedding_vector
Revises: 0047_rfp_reference_doc
Create Date: 2026-09-03

Replaces the JSON `embedding` column as the retrieval path's source for similarity search on
Postgres. `embedding` itself is untouched and remains the source of truth for writes (ingest
still only writes JSON; this column is backfilled once here and kept in sync by
SqlVectorStore.add_all going forward - see app/db/stores.py). No-op on SQLite, same pattern as
0004_pgvector.py: dev/tests keep today's exact JSON + Python-ranking behavior.

Verified against real data before writing this migration (read-only, approved production ops
scope): 3,514 rows on live, 4,280 on preprod, `vector` extension already active on both
(0.8.5 live, 0.8.4 preprod) via 0004_pgvector.py. At this size a single-transaction ALTER TABLE +
UPDATE + CREATE INDEX (no CONCURRENTLY, no batching) completes in well under a second - see the
design spec `.devin/specs/2026-09-03-passage-vector-retrieval-scaling-design.md` for the full
reasoning on why that added complexity is not justified by this data.
"""
from alembic import op

revision = "0048_passage_embedding_vector"
down_revision = "0047_rfp_reference_doc"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024  # Settings.embeddings_dim default (Titan V2) - see app/core/config.py


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE passages ADD COLUMN embedding_vec vector({EMBEDDING_DIM})")
    op.execute(
        "UPDATE passages SET embedding_vec = CAST(embedding::text AS vector) "
        f"WHERE embedding_vec IS NULL AND json_array_length(embedding) = {EMBEDDING_DIM}"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_passages_embedding_vec_hnsw "
        "ON passages USING hnsw (embedding_vec vector_cosine_ops)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_passages_embedding_vec_hnsw")
    op.execute("ALTER TABLE passages DROP COLUMN IF EXISTS embedding_vec")
