"""Per-admin platform capabilities plus an append-only grant audit (QIK-513).

The two coarse roles (super_admin/viewer) stay, but several admin surfaces are specified as
"permission-restricted" (AI spend, system stats, cost caps) and "super_admin or nothing" is too
blunt for those. capabilities is NULL for every existing row, which means "use the role default",
so current behaviour is unchanged until an explicit grant is made.

Platform admin is the highest privilege in the system and had no audit trail at all; the audit
table mirrors agent_state_audit.
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_platform_admin_capabilities"
down_revision = "0031_passage_agent_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_admins", sa.Column("capabilities", sa.JSON(), nullable=True))
    op.create_table(
        "platform_admin_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("changed_by_email", sa.String(320), nullable=False),
        sa.Column("previous_role", sa.String(16), nullable=True),
        sa.Column("role", sa.String(16), nullable=True),
        sa.Column("previous_capabilities", sa.JSON(), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_platform_admin_audit_email", "platform_admin_audit", ["email"])
    op.create_index("ix_platform_admin_audit_created_at", "platform_admin_audit", ["created_at"])
    op.create_index("ix_platform_admin_audit_email_created", "platform_admin_audit",
                    ["email", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_admin_audit_email_created", table_name="platform_admin_audit")
    op.drop_index("ix_platform_admin_audit_created_at", table_name="platform_admin_audit")
    op.drop_index("ix_platform_admin_audit_email", table_name="platform_admin_audit")
    op.drop_table("platform_admin_audit")
    op.drop_column("platform_admins", "capabilities")
