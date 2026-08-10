"""The append-only boundary on audit_events.

This is the half of the immutability story that carries the claim. The daily WORM export answers "a copy
the database administrators cannot alter"; this answers "the application cannot alter historic rows",
which is what an ISO auditor asks about directly.

WHAT CAN AND CANNOT BE TESTED HERE. The enforcement is a Postgres grant, and the suite runs on SQLite,
which has neither roles nor per-table grants. So these tests cover the SHAPE: that the migration is
guarded to Postgres, that it refuses to revoke before a maintenance role exists, that the jobs and the
one privileged endpoint use the maintenance connection, and that nothing else does. The grant itself is
verified on preprod with `\\dp audit_events`, recorded in the ledger. Saying which half is covered by
tests and which by an operator check is the honest version of "append-only".
"""
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0039_audit_append_only.py"


@pytest.fixture(scope="module")
def migration() -> str:
    return MIGRATION.read_text()


def test_the_migration_is_a_no_op_on_sqlite(migration):
    """SQLite has no roles and no per-table grants, so there is nothing to enforce and the suite would
    fail on the syntax. A test asserts the guard, which is the honest limit of local coverage."""
    assert 'dialect.name == "postgresql"' in migration
    assert migration.count("if not _is_postgres():") >= 2, "upgrade and downgrade both need the guard"


def test_it_refuses_to_revoke_before_the_maintenance_role_exists(migration):
    """The important property. Retention legitimately needs UPDATE and DELETE, so revoking before a
    second role exists leaves it failing silently, and the trail then grows personal data indefinitely
    while the code claims a policy it can no longer enforce. That is worse than not having the boundary.
    """
    assert "SELECT 1 FROM pg_roles WHERE rolname = :role" in migration
    assert migration.index("if not role_exists:") < migration.index("REVOKE UPDATE, DELETE, TRUNCATE")
    # A notice, not a failure: failing would block every unrelated deploy on a manual operations step.
    assert "print(f\"NOTICE:" in migration


def test_the_maintenance_role_is_granted_before_the_app_role_is_revoked(migration):
    """Otherwise there is a window in which nothing can run retention."""
    assert migration.index('GRANT INSERT, SELECT, UPDATE, DELETE ON audit_events') < migration.index(
        "REVOKE UPDATE, DELETE, TRUNCATE")


def test_truncate_is_revoked_too(migration):
    """It is the cheapest way to destroy the whole table and revoking DELETE does not cover it."""
    assert "TRUNCATE" in migration


def test_insert_and_select_stay_explicit(migration):
    """The application still has to be able to write and read the trail. Explicit rather than assumed,
    because a REVOKE that accidentally took INSERT would stop every audit row on the platform."""
    assert "GRANT INSERT, SELECT ON audit_events" in migration


def test_the_downgrade_restores_the_grants_and_touches_no_data(migration):
    """Which is why this is safe to try on preprod first."""
    downgrade = migration[migration.index("def downgrade"):]
    assert "GRANT UPDATE, DELETE, TRUNCATE ON audit_events" in downgrade
    for destructive in ("DELETE FROM", "DROP TABLE", "TRUNCATE TABLE", "UPDATE audit_events"):
        assert destructive not in downgrade


def test_the_retention_and_archive_jobs_use_the_maintenance_connection():
    """They are the only things that legitimately UPDATE or DELETE audit rows."""
    worker = (Path(__file__).resolve().parents[1] / "app" / "tasks" / "worker.py").read_text()
    retention = worker[worker.index("async def apply_audit_retention"):]
    assert 'ctx.get("audit_sessionmaker")' in retention.split("async def ")[1]
    archive = worker[worker.index("async def export_audit_archive"):]
    assert 'ctx.get("audit_sessionmaker")' in archive.split("async def ")[1]


def test_an_unset_maintenance_url_falls_back_so_the_two_can_ship_apart():
    """The migration is a no-op until the role exists, and the wiring is a no-op until the URL is set.
    Either order is safe, which is the property that makes this mergeable without a live change."""
    from app.core.config import Settings

    assert Settings().audit_maint_database_url == ""
    worker = (Path(__file__).resolve().parents[1] / "app" / "tasks" / "worker.py").read_text()
    assert 'ctx["audit_sessionmaker"] = ctx["sessionmaker"]' in worker


def test_only_the_erase_endpoint_reaches_the_privileged_store():
    """Erasure is a legal obligation, so it has to work under the boundary, and it is the one handler
    that UPDATEs audit_events.

    The trade is stated in main.py rather than hidden: the API process does hold a connection able to
    rewrite history. What the boundary buys is that every instrumented write path goes through
    app.state.audit, so rewriting history is reachable from exactly one manage_admins-gated handler
    instead of from anywhere. This test is what keeps that "exactly one" true.
    """
    modules = Path(__file__).resolve().parents[1] / "app" / "modules"
    # Matched on the attribute NAME, not on `state.audit_maint`: it is reached through getattr, so the
    # dotted form never appears. The first version of this test searched for the dotted form, found
    # nothing, and would have stayed green however many handlers took the privileged store.
    users = sorted(path.relative_to(modules).as_posix() for path in modules.rglob("*.py")
                   if "audit_maint" in path.read_text())
    assert users == ["admin/router.py"], f"only the admin router may use the maintenance store: {users}"

    admin = (modules / "admin" / "router.py").read_text()
    handlers = [block.split("(")[0] for block in admin.split("async def ")[1:]
                if "audit_maint" in block]
    assert handlers == ["erase_subject"], f"unexpected handlers hold the privileged store: {handlers}"


def test_the_api_never_reads_the_maintenance_url_outside_that_one_wiring():
    """A setting the API does not load cannot be reached by accident."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    readers = sorted(path.relative_to(app_dir).as_posix() for path in app_dir.rglob("*.py")
                     if "audit_maint_database_url" in path.read_text())
    assert readers == ["core/config.py", "main.py", "tasks/worker.py"], readers
