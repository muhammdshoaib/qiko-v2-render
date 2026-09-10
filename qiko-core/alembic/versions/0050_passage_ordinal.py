"""Give every passage its position within its document, so retrieval can widen a hit into the
contiguous run of text around it (QIKO-1085).

A tender's substance lives in tables, and an 800-character window cuts a thirteen-row table into
six chunks. Retrieval returns some of them, the model sees a fragment, and the answer comes back
naming nine of thirteen projects. Knowing which chunks sit next to each other is what lets the
retriever hand over the whole table instead.

Backfilled rather than requiring a re-ingest. `KnowledgeService.ingest` derives each id as
sha1(f"{tenant}:{agent_id or ''}:{doc_id}:{i}")[:16] with `i` the chunk index, so the ordinal is
recoverable by recomputing that hash for i = 0..n-1 per (tenant, agent, doc) and matching ids. No
text is re-chunked and no embedding is recomputed, which matters because re-embedding every
customer corpus would be a real spend and would change retrieval for everyone at once.

That reconstruction is deliberately confined to this migration. Afterwards the column is
authoritative and nothing else depends on how ids are built.

Revision ID: 0050_passage_ordinal
Revises: 0049_investor_activity_events
"""
from __future__ import annotations

import hashlib

import sqlalchemy as sa
from alembic import op

revision = "0050_passage_ordinal"
down_revision = "0049_investor_activity_events"
branch_labels = None
depends_on = None

# Room beyond the observed count when probing, so a document with a few deleted chunks still has
# the rest of its ordinals recovered rather than the scan stopping at the first miss.
_PROBE_SLACK = 64


def upgrade() -> None:
    op.add_column("passages", sa.Column("ordinal", sa.Integer(), nullable=True))

    bind = op.get_bind()
    groups = bind.execute(sa.text(
        "select tenant_id, coalesce(agent_id, ''), doc_id, count(*) "
        "from passages group by tenant_id, coalesce(agent_id, ''), doc_id"
    )).fetchall()

    for tenant_id, agent_key, doc_id, count in groups:
        # The id seed uses the raw agent_id, which is '' for tenant-wide passages, so agent_key is
        # already the right value to hash with.
        mapping = {}
        for i in range(int(count) + _PROBE_SLACK):
            seed = f"{tenant_id}:{agent_key}:{doc_id}:{i}"
            mapping[hashlib.sha1(seed.encode()).hexdigest()[:16]] = i
        if not mapping:
            continue
        rows = bind.execute(sa.text(
            "select id from passages where tenant_id = :t and coalesce(agent_id, '') = :a "
            "and doc_id = :d"
        ), {"t": tenant_id, "a": agent_key, "d": doc_id}).fetchall()
        for (pid,) in rows:
            ordinal = mapping.get(pid)
            if ordinal is None:
                # Ingested under a different id scheme, or hand-inserted. Left null: retrieval
                # treats a null ordinal as unwidenable and falls back to the single passage, which
                # is exactly today's behaviour.
                continue
            bind.execute(sa.text("update passages set ordinal = :o where id = :i"),
                         {"o": ordinal, "i": pid})

    op.create_index("ix_passages_doc_ordinal", "passages",
                    ["tenant_id", "doc_id", "ordinal"])


def downgrade() -> None:
    op.drop_index("ix_passages_doc_ordinal", table_name="passages")
    op.drop_column("passages", "ordinal")
