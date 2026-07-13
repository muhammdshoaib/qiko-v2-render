"""sales_intel_* tables (IDG Sales Intelligence -- UNGM/TED ingestion, qualification, human
review, Salesforce push), ported from the unmerged qiko-backend origin/idg-sales Laravel branch
(idg_sales_ingestion_sources / idg_sales_opportunities / idg_sales_activity_logs /
idg_sales_salesforce_connections migrations).

Revision ID: 0015_sales_intelligence
Revises: 0014_crm_contacts
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_sales_intelligence"
down_revision = "0014_crm_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales_intel_ingestion_sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("source_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(40), nullable=False, server_default="portal"),
        sa.Column("status", sa.String(40), nullable=False, server_default="inactive"),
        sa.Column("auth_status", sa.String(80), nullable=True),
        sa.Column("scan_cadence", sa.String(80), nullable=False, server_default="manual"),
        sa.Column("last_scan_status", sa.String(40), nullable=True),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opportunities_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sales_intel_source_agent", "sales_intel_ingestion_sources",
                    ["tenant_id", "agent_id", "source_key"], unique=True)

    op.create_table(
        "sales_intel_opportunities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("source_key", sa.String(80), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("buyer", sa.String(255), nullable=True),
        sa.Column("country", sa.String(255), nullable=True),
        sa.Column("region", sa.String(255), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("estimated_value", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage", sa.String(80), nullable=False, server_default="ingested"),
        sa.Column("recommendation", sa.String(40), nullable=True),
        sa.Column("qualification_score", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("competitor_readiness", sa.String(40), nullable=True),
        sa.Column("qualification_summary", sa.String(), nullable=True),
        sa.Column("qualification_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("qualification_dimensions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("qualification_recommendations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rejection_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("risks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("missing_fields", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("human_review_status", sa.String(40), nullable=True),
        sa.Column("human_review_notes", sa.String(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.String(64), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(64), nullable=True),
        sa.Column("salesforce_push_status", sa.String(40), nullable=False, server_default="not_started"),
        sa.Column("salesforce_opportunity_id", sa.String(255), nullable=True),
        sa.Column("salesforce_pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("salesforce_push_error", sa.String(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sales_intel_opp_source_external", "sales_intel_opportunities",
                    ["tenant_id", "agent_id", "source_key", "external_id"], unique=True)
    op.create_index("ix_sales_intel_opp_agent_stage", "sales_intel_opportunities",
                    ["tenant_id", "agent_id", "stage"])

    op.create_table(
        "sales_intel_activity_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("opportunity_id", sa.String(64), nullable=True),
        sa.Column("actor_user_id", sa.String(64), nullable=True),
        sa.Column("activity_type", sa.String(40), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("tone", sa.String(40), nullable=False, server_default="info"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sales_intel_log_agent_created", "sales_intel_activity_logs",
                    ["tenant_id", "agent_id", "created_at"])
    op.create_index("ix_sales_intel_log_opportunity", "sales_intel_activity_logs", ["opportunity_id"])

    op.create_table(
        "sales_intel_salesforce_connections",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="disconnected"),
        sa.Column("instance_url", sa.String(500), nullable=True),
        sa.Column("enc_access_token", sa.String(), nullable=True),
        sa.Column("enc_refresh_token", sa.String(), nullable=True),
        sa.Column("token_type", sa.String(40), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("salesforce_user_id", sa.String(255), nullable=True),
        sa.Column("salesforce_org_id", sa.String(255), nullable=True),
        sa.Column("connected_by_user_id", sa.String(64), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sales_intel_salesforce_connections")
    op.drop_index("ix_sales_intel_log_opportunity", table_name="sales_intel_activity_logs")
    op.drop_index("ix_sales_intel_log_agent_created", table_name="sales_intel_activity_logs")
    op.drop_table("sales_intel_activity_logs")
    op.drop_index("ix_sales_intel_opp_agent_stage", table_name="sales_intel_opportunities")
    op.drop_index("ix_sales_intel_opp_source_external", table_name="sales_intel_opportunities")
    op.drop_table("sales_intel_opportunities")
    op.drop_index("ix_sales_intel_source_agent", table_name="sales_intel_ingestion_sources")
    op.drop_table("sales_intel_ingestion_sources")
