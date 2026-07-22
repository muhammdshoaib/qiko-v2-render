"""durable billing stores + admin customer flags

Makes the billing lifecycle state durable (Postgres-backed) so it survives a restart in
production, and adds the per-tenant admin-customer flag row that backs the Studio/soft-delete
toggles for the (otherwise fully derived) admin Customers console:

* billing_subscriptions        - subscriptions (subject/plan/status/period)
* billing_stripe_customers     - the tenant <-> Stripe customer id mapping
* billing_invoices             - Stripe invoices synced by the webhook (idempotent by id)
* billing_payment_links        - admin-created payment links + their logged lifecycle
* admin_customer_flags         - per-tenant Studio-access + soft-delete flags

Revision ID: 0024_billing_durability_and_admin_customers
Revises: 0023_otp_and_pending_invites
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_billing_durability_and_admin_customers"
down_revision = "0023_otp_and_pending_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_subscriptions",
        sa.Column("subject", sa.String(64), primary_key=True),
        sa.Column("plan", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "billing_stripe_customers",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("stripe_customer_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "billing_invoices",
        sa.Column("stripe_invoice_id", sa.String(255), primary_key=True),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_billing_invoices_customer_id", "billing_invoices", ["customer_id"])

    op.create_table(
        "billing_payment_links",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("customer_email", sa.String(320), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_billing_payment_links_customer_email", "billing_payment_links", ["customer_email"])

    op.create_table(
        "admin_customer_flags",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("is_studio", sa.Boolean(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("admin_customer_flags")
    op.drop_index("ix_billing_payment_links_customer_email", table_name="billing_payment_links")
    op.drop_table("billing_payment_links")
    op.drop_index("ix_billing_invoices_customer_id", table_name="billing_invoices")
    op.drop_table("billing_invoices")
    op.drop_table("billing_stripe_customers")
    op.drop_table("billing_subscriptions")
