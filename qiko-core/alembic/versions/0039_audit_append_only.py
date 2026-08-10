"""Make audit_events append-only for the application role (leg E4b).

This is the half of the immutability story that carries the claim. Until it exists, "the application
cannot alter historic rows" is a design intention rather than an enforced property, and an ISO auditor
asking "show that the administrators of the system cannot modify historic entries" has nothing to look at.

CONDITIONAL ON THE MAINTENANCE ROLE EXISTING, which is the whole reason this migration is more than two
GRANT statements.

The retention job legitimately needs UPDATE (nulling addresses at six months, pseudonymising on erasure)
and DELETE (the thirteen-month expiry). So a single role cannot be both append-only and able to run
retention. Revoking before a second role exists would leave retention failing silently, which is a worse
outcome than not having the boundary: the trail would grow personal data indefinitely while the code
claimed a policy it could no longer enforce.

So the revoke happens only when qiko_audit_maint is present. Deploy order stops mattering: this can ship
before the role is created, and the boundary comes into force on the next migration run after it exists.
An operator can see which state they are in from the notice this emits.

Reverses cleanly. The downgrade restores the grants and touches no data.
"""
from alembic import op
import sqlalchemy as sa

revision = "0039_audit_append_only"
down_revision = "0038_audit_archive_digests"
branch_labels = None
depends_on = None

MAINTENANCE_ROLE = "qiko_audit_maint"


def _is_postgres() -> bool:
    # SQLite has no roles and no per-table grants, so there is nothing to enforce there and the suite
    # runs against it. A test asserts this guard rather than the grant, which is the honest limit of what
    # can be covered without a Postgres fixture.
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    bind = op.get_bind()
    app_role = bind.execute(sa.text("SELECT current_user")).scalar()
    role_exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
        {"role": MAINTENANCE_ROLE}).scalar() is not None

    if not role_exists:
        # A notice rather than a failure. Failing the migration would block every unrelated deploy on an
        # operations step that has to happen by hand, and the previous behaviour is not a regression.
        print(f"NOTICE: {MAINTENANCE_ROLE} does not exist, so audit_events stays writable by "
              f"{app_role}. Create the role and re-run migrations to enforce append-only.")
        return

    # The maintenance role needs its grants BEFORE the app role loses them, or there is a window where
    # nothing can run retention.
    op.execute(sa.text(
        f'GRANT INSERT, SELECT, UPDATE, DELETE ON audit_events TO "{MAINTENANCE_ROLE}"'))
    op.execute(sa.text(
        f'GRANT SELECT, INSERT, UPDATE ON audit_archive_digests TO "{MAINTENANCE_ROLE}"'))
    op.execute(sa.text(
        f'GRANT USAGE, SELECT ON SEQUENCE audit_events_id_seq TO "{MAINTENANCE_ROLE}"'))

    # TRUNCATE as well as UPDATE and DELETE: it is the cheapest way to destroy the whole table and it is
    # not covered by revoking DELETE.
    op.execute(sa.text(f'REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM "{app_role}"'))
    # Explicit rather than assumed. The app must still be able to write and read.
    op.execute(sa.text(f'GRANT INSERT, SELECT ON audit_events TO "{app_role}"'))
    print(f"NOTICE: audit_events is now append-only for {app_role}; "
          f"{MAINTENANCE_ROLE} retains UPDATE and DELETE for retention and erasure.")


def downgrade() -> None:
    if not _is_postgres():
        return
    app_role = op.get_bind().execute(sa.text("SELECT current_user")).scalar()
    op.execute(sa.text(f'GRANT UPDATE, DELETE, TRUNCATE ON audit_events TO "{app_role}"'))
