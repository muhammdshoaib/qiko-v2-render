"""leads, teams, team_members tables

Revision ID: 0010_leads_teams
Revises: 0009_rfp_pack_document_text
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_leads_teams"
down_revision = "0009_rfp_pack_document_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_index("ix_leads_email", "leads", ["email"])

    op.create_table(
        "teams",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_teams_tenant_id", "teams", ["tenant_id"])

    op.create_table(
        "team_members",
        sa.Column("team_id", sa.String(64), sa.ForeignKey("teams.id"), primary_key=True),
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("team_members")
    op.drop_index("ix_teams_tenant_id", table_name="teams")
    op.drop_table("teams")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_index("ix_leads_tenant_id", table_name="leads")
    op.drop_table("leads")
