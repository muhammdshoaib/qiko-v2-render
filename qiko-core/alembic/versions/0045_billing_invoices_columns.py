"""Extend billing invoices with Stripe currency, number, urls and period.

The webhook only kept the bare minimum (customer, amount, status). The admin
invoice list needs a human invoice number, currency, hosted invoice URL, PDF
link and the period the invoice covers.
"""
from alembic import op
import sqlalchemy as sa

revision = "0045_billing_invoices_columns"
down_revision = "0044_webhook_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("billing_invoices", sa.Column("currency", sa.String(3), nullable=True))
    op.add_column("billing_invoices", sa.Column("number", sa.String(255), nullable=True))
    op.add_column("billing_invoices", sa.Column("hosted_invoice_url", sa.Text, nullable=True))
    op.add_column("billing_invoices", sa.Column("invoice_pdf", sa.Text, nullable=True))
    op.add_column("billing_invoices", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_invoices", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in ("period_end", "period_start", "invoice_pdf",
                "hosted_invoice_url", "number", "currency"):
        op.drop_column("billing_invoices", col)
