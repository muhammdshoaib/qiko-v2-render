"""Per-day digests for the audit archive (leg E4b).

The write-once export is the copy that matters for tamper evidence, because an attacker with database
access can rewrite this table. It exists so a run can chain onto the previous day without a network round
trip, and so an operator can see what has been exported without listing a bucket.
"""
from alembic import op
import sqlalchemy as sa

revision = "0038_audit_archive_digests"
down_revision = "0037_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_archive_digests",
        # The day IS the key: one export per day, and re-running must overwrite rather than duplicate.
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("previous_digest", sa.String(64), nullable=True),
        sa.Column("object_key", sa.String(255), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_archive_digests")
