"""Audit the admin mutations that left no trace (QIK admin overhaul, leg B).

Three platform-admin mutations were unaudited: the Studio toggle, the customer soft delete, and
cost-cap set/delete. Soft delete hides a tenant platform-wide and has no reversal endpoint; a cost cap
can stop a customer's workers answering. Deleting a cap also deleted its updated_by_email, so the only
record of who had set it went with it.

Generic rather than shape-specific, because the two existing audit tables each model one mutation and a
third narrow table would have meant a fourth next time.
"""
from alembic import op
import sqlalchemy as sa

revision = "0036_admin_action_audit"
down_revision = "0035_ai_cost_caps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_action_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(320), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("actor_email", sa.String(320), nullable=False),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_action_audit_action", "admin_action_audit", ["action"])
    op.create_index("ix_admin_action_audit_target_id", "admin_action_audit", ["target_id"])
    op.create_index("ix_admin_action_audit_tenant_id", "admin_action_audit", ["tenant_id"])
    op.create_index("ix_admin_action_audit_actor_email", "admin_action_audit", ["actor_email"])
    op.create_index("ix_admin_action_audit_created_at", "admin_action_audit", ["created_at"])


def downgrade() -> None:
    op.drop_table("admin_action_audit")
