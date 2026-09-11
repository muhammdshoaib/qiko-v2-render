"""Persist Joseph Mews generations by requestId, so idempotency and outcome reporting survive a
restart and more than one replica.

JM2-1131 shipped three in-memory caches (`_cache`, `_insight_cache`, `_portfolio_insight_cache`)
and two in-memory outcome logs. Their docstrings were honest about the tradeoff ("fine for a
single replica, needs Redis before scaling out"), but it has a consequence nobody had hit yet and
Shoaib hit while integrating: `POST /insights/{requestId}/outcome` 404s with "unknown requestId"
for anything generated before the last deploy, because the cache the lookup goes through is gone.
Every outcome report is therefore lost across a release, and the numbers `/outcomes/summary`
reports silently reset to zero.

It also left the app unable to re-read a generated insight at all: the only way to get one back
was to re-POST the same requestId and hope the process had not restarted. This table is what
`GET /insights/property` reads.

A row exists means "this requestId was generated". `result` NULL on an existing row means the
generation itself failed, which is a distinct state from never having been asked: the router
returns GENERATION_FAILED for the former and drafts fresh for the latter, and conflating them
would make a failed generation retry forever.

Revision ID: 0052_jm_generations
Revises: 0051_pipeline_verdict
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0052_jm_generations"
down_revision = "0051_pipeline_verdict"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jm_generations",
        sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        # 'signal' | 'property_insight' | 'portfolio_insight'. Plain string rather than a DB enum
        # so adding a fourth generation kind is a code change, not a migration.
        sa.Column("kind", sa.String(32), nullable=False),
        # NULL means the generation was attempted and failed. See the module docstring.
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
                  nullable=True),
        # Lookup keys for GET /insights/property. Name/location/postcode rather than any id,
        # matching the identity rule the activity module already enforces.
        sa.Column("investor_ref", sa.String(128), nullable=True),
        sa.Column("property_name", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("postcode", sa.String(16), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("outcome_note", sa.String(2000), nullable=False, server_default=""),
        sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    # Serves the GET: newest generation for one investor+property within a tenant.
    op.create_index("ix_jm_generations_lookup", "jm_generations",
                    ["tenant_id", "kind", "investor_ref", "property_name", "created_at"])
    # Serves /outcomes/summary without scanning the table.
    op.create_index("ix_jm_generations_outcome", "jm_generations",
                    ["tenant_id", "kind", "outcome"])


def downgrade() -> None:
    op.drop_index("ix_jm_generations_outcome", table_name="jm_generations")
    op.drop_index("ix_jm_generations_lookup", table_name="jm_generations")
    op.drop_table("jm_generations")
