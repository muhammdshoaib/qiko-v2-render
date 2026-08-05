"""Per-tenant, per-worker AI token and cost accounting (QIK-514).

Nothing recorded LLM spend before this: Bedrock returns a usage block on every Converse call and
Titan returns inputTextTokenCount, and both were read for their text or vector and thrown away. So
there was no way to answer "what is this customer costing us", which is the prerequisite for the
cost dashboard, worker monitoring and cost caps.

tenant_id and agent_id are nullable on purpose. Several call sites (background tender generation,
public embed chat) have no bound worker, and dropping an event that has already been billed by AWS
would be worse than recording it as unattributed.
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_ai_usage_events"
down_revision = "0032_platform_admin_capabilities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("priced", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_usage_events_tenant_id", "ai_usage_events", ["tenant_id"])
    op.create_index("ix_ai_usage_events_agent_id", "ai_usage_events", ["agent_id"])
    op.create_index("ix_ai_usage_events_created_at", "ai_usage_events", ["created_at"])
    op.create_index("ix_ai_usage_tenant_created", "ai_usage_events", ["tenant_id", "created_at"])
    op.create_index("ix_ai_usage_tenant_agent_created", "ai_usage_events",
                    ["tenant_id", "agent_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_tenant_agent_created", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_tenant_created", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_created_at", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_agent_id", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_tenant_id", table_name="ai_usage_events")
    op.drop_table("ai_usage_events")
