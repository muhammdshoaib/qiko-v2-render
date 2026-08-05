"""Rescale AI usage cost from micro-USD to nano-USD (QIK-514 follow-up).

A live check against Bedrock exposed two defects in the first cut:

1. Micro-USD rounds real calls to zero. Titan v2 costs 20 micro-USD per 1,000 tokens, so an 8-token
   embedding priced at 0.16 and rounded away. An ingest embeds every chunk of every document, so an
   entire corpus would have appeared free.
2. The price table was keyed on the configured model name, but Bedrock resolves to a date-and-version
   qualified id ("eu.anthropic.claude-sonnet-4-5-20250929-v1:0"), so exact matching failed on every
   real call and recorded priced=False with zero cost.

This migration handles (1); (2) is a code change to longest-prefix matching. Safe to rename rather
than migrate values: the table is empty in every environment.
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_ai_usage_nano_usd"
down_revision = "0033_ai_usage_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("ai_usage_events", "cost_micro_usd", new_column_name="cost_nano_usd",
                    existing_type=sa.BigInteger(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("ai_usage_events", "cost_nano_usd", new_column_name="cost_micro_usd",
                    existing_type=sa.BigInteger(), existing_nullable=False)
