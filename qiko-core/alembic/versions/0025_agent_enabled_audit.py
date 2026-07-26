"""Add durable worker enabled state and append-only transition audit."""
from alembic import op
import sqlalchemy as sa

revision = "0025_agent_enabled_audit"
down_revision = "0024_billing_durability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(sa.text("UPDATE agents SET enabled = true WHERE enabled IS NULL"))
    op.create_table(
        "agent_state_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("changed_by_email", sa.String(320), nullable=False),
        sa.Column("previous_enabled", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_state_audit_tenant_id", "agent_state_audit", ["tenant_id"])
    op.create_index("ix_agent_state_audit_agent_id", "agent_state_audit", ["agent_id"])
    op.create_index("ix_agent_state_audit_created_at", "agent_state_audit", ["created_at"])
    op.create_index(
        "ix_agent_state_audit_tenant_agent_created",
        "agent_state_audit",
        ["tenant_id", "agent_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_state_audit_tenant_agent_created", table_name="agent_state_audit")
    op.drop_index("ix_agent_state_audit_created_at", table_name="agent_state_audit")
    op.drop_index("ix_agent_state_audit_agent_id", table_name="agent_state_audit")
    op.drop_index("ix_agent_state_audit_tenant_id", table_name="agent_state_audit")
    op.drop_table("agent_state_audit")
    op.drop_column("agents", "enabled")
