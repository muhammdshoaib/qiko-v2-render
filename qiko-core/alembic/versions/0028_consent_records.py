"""Add immutable policy releases, append-only consent evidence, and pending signups."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0028_consent_records"
down_revision = "0027_mfa_backup_codes"
branch_labels = None
depends_on = None

_RELEASES = (
    ("terms-2026-07-24", "terms", "0005d9a75e20191854111bdfc210abe8f6bc965e2925103efdff2541fe37b813"),
    ("privacy-2026-07-24", "privacy", "2a80152571cbc4b855edd995ee9de978ba967adeeedd2f6f3352f8fd5a30aadc"),
    ("cookies-2026-07-24", "cookies", "2db07436eef3b54526a20e65358c7d3f62fedeceddca332ecd7bb371688abb0c"),
)


def _create_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table in ("policy_releases", "consent_records"):
            for operation in ("UPDATE", "DELETE"):
                name = f"trg_{table}_reject_{operation.lower()}"
                op.execute(sa.text(
                    f"CREATE TRIGGER {name} BEFORE {operation} ON {table} "
                    f"BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END"
                ))
        return

    op.execute(sa.text("""
        CREATE FUNCTION reject_immutable_legal_record() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
    """))
    for table in ("policy_releases", "consent_records"):
        for operation in ("UPDATE", "DELETE"):
            name = f"trg_{table}_reject_{operation.lower()}"
            op.execute(sa.text(
                f"CREATE TRIGGER {name} BEFORE {operation} ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION reject_immutable_legal_record()"
            ))


def upgrade() -> None:
    op.create_table(
        "policy_releases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("policy_type", sa.String(16), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("policy_type IN ('terms', 'privacy', 'cookies')", name="ck_policy_release_type"),
    )
    policy_table = sa.table(
        "policy_releases",
        sa.column("id", sa.String),
        sa.column("policy_type", sa.String),
        sa.column("content_sha256", sa.String),
        sa.column("effective_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    effective_at = datetime(2026, 7, 24, tzinfo=timezone.utc)
    op.bulk_insert(policy_table, [
        {
            "id": release_id,
            "policy_type": policy_type,
            "content_sha256": digest,
            "effective_at": effective_at,
            "created_at": effective_at,
        }
        for release_id, policy_type, digest in _RELEASES
    ])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("decision_id", sa.String(128), nullable=False, unique=True),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("client_revision", sa.BigInteger(), nullable=False),
        sa.Column("key_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("subject_hmac", sa.String(64), nullable=False),
        sa.Column("preferences", sa.Boolean(), nullable=False),
        sa.Column("analytics", sa.Boolean(), nullable=False),
        sa.Column("marketing", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("terms_release_id", sa.String(64), sa.ForeignKey("policy_releases.id"), nullable=False),
        sa.Column("privacy_release_id", sa.String(64), sa.ForeignKey("policy_releases.id"), nullable=False),
        sa.Column("cookies_release_id", sa.String(64), sa.ForeignKey("policy_releases.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('anonymous', 'authenticated', 'signup')", name="ck_consent_source"),
        sa.CheckConstraint("action IN ('accept', 'reject', 'update', 'withdraw')", name="ck_consent_action"),
    )
    op.create_index("ix_consent_records_decision_id", "consent_records", ["decision_id"], unique=True)
    op.create_index("ix_consent_records_revision", "consent_records", ["revision"])
    op.create_index("ix_consent_records_client_revision", "consent_records", ["client_revision"])
    op.create_index("ix_consent_records_subject_hmac", "consent_records", ["subject_hmac"])
    op.create_index("uq_consent_subject_revision", "consent_records", ["subject_hmac", "revision"], unique=True)
    op.create_index("ix_consent_records_created_at", "consent_records", ["created_at"])
    op.create_index("ix_consent_subject_created", "consent_records", ["subject_hmac", "created_at"])

    op.create_table(
        "pending_signups",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts_remaining", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_team_id", sa.String(64), nullable=True),
        sa.Column("terms_release_id", sa.String(64), sa.ForeignKey("policy_releases.id"), nullable=False),
        sa.Column("privacy_release_id", sa.String(64), sa.ForeignKey("policy_releases.id"), nullable=False),
        sa.Column("cookies_release_id", sa.String(64), sa.ForeignKey("policy_releases.id"), nullable=False),
        sa.Column("invite_version", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pending_signups_expires_at", "pending_signups", ["expires_at"])
    _create_immutability_triggers()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect != "sqlite":
        for table in ("policy_releases", "consent_records"):
            for operation in ("UPDATE", "DELETE"):
                op.execute(sa.text(f"DROP TRIGGER trg_{table}_reject_{operation.lower()} ON {table}"))
        op.execute(sa.text("DROP FUNCTION reject_immutable_legal_record()"))
    op.drop_index("ix_pending_signups_expires_at", table_name="pending_signups")
    op.drop_table("pending_signups")
    op.drop_index("ix_consent_subject_created", table_name="consent_records")
    op.drop_index("ix_consent_records_created_at", table_name="consent_records")
    op.drop_index("uq_consent_subject_revision", table_name="consent_records")
    op.drop_index("ix_consent_records_subject_hmac", table_name="consent_records")
    op.drop_index("ix_consent_records_client_revision", table_name="consent_records")
    op.drop_index("ix_consent_records_revision", table_name="consent_records")
    op.drop_index("ix_consent_records_decision_id", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_table("policy_releases")
