"""The rollout of the append-only boundary, as a reviewable script rather than a typed procedure.

Enabling it is a four-step privilege change with an ordering constraint: the maintenance role must exist
AND the worker must be able to reach it before the application role loses UPDATE and DELETE. Get that
wrong and retention stops working, which means the trail quietly accumulates personal data past the
policy the code still reports. Typed by hand, in two environments, weeks apart, the order is exactly what
gets forgotten.

These tests read the script. That is a weaker check than running it, and there is no way to run it here:
it needs a Postgres with roles, a docker compose project and an SSM host. What can be pinned is the
ordering, the idempotency, and that no secret reaches a log or a command line. The grants themselves are
verified by the script's own final step, whose output is the evidence.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "deploy" / "enable-audit-append-only.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "enable-audit-append-only.yml"


@pytest.fixture(scope="module")
def script() -> str:
    return SCRIPT.read_text()


@pytest.fixture(scope="module")
def workflow() -> str:
    return WORKFLOW.read_text()


def test_the_worker_gets_the_connection_before_the_revoke(script):
    """The ordering constraint the whole script exists for. The migration grants the maintenance role
    before revoking, but the WORKER also has to be running with the new URL, or retention fails with a
    permission error on its next tick and the failure is a log line nobody reads."""
    env_write = script.index("AUDIT_MAINT_DATABASE_URL=%s")
    restart = script.index("up -d --no-deps worker")
    migrate = script.index("alembic upgrade head")
    assert env_write < restart < migrate


def test_it_stops_before_the_revoke_if_the_worker_will_not_start(script):
    """Continuing would revoke UPDATE from the application while nothing else can perform it."""
    restart_block = script[script.index("up -d --no-deps worker"):script.index("alembic upgrade head")]
    assert "not proceeding to the revoke" in restart_block
    assert "exit 1" in restart_block


def test_the_password_is_generated_on_the_box(script):
    """So it never exists in CI logs, a GitHub secret, or an agent transcript. A password that has been
    in a transcript is a password that has to be rotated before the control means anything."""
    assert "openssl rand" in script
    assert "MAINT_PASSWORD" in script
    # Never echoed, and never interpolated into a shell command where it would land in the process table.
    assert "echo $MAINT_PASSWORD" not in script and 'echo "$MAINT_PASSWORD"' not in script
    assert "PASSWORD $MAINT_PASSWORD" not in script


def test_the_secret_reaches_postgres_through_the_servers_own_quoting(script):
    """CREATE ROLE cannot take a bound parameter for a password, which is where this kind of script
    usually starts formatting SQL strings. quote_literal on the server side is the alternative that does
    not."""
    assert "quote_literal(:s)" in script
    assert "quote_ident(:r)" in script
    # The role name is bound as a parameter for the existence check rather than concatenated.
    assert "WHERE rolname = :r" in script


def test_the_maintenance_url_is_derived_from_the_application_url(script):
    """Hand-writing it invites a typo that points retention at the wrong database, and a retention job
    pointed at the wrong database is a delete against the wrong data."""
    assert "APP_URL=" in script
    assert 'TAIL="${APP_URL#*@}"' in script
    assert "no credentials section" in script, "a malformed URL must stop rather than build a wrong one"


def test_connect_is_granted_as_well_as_the_table_privileges(script):
    """Easy to forget, and without it the worker fails at the handshake rather than at the query, which
    reads as an outage instead of a missing grant."""
    assert "GRANT CONNECT ON DATABASE" in script


def test_it_is_idempotent(script):
    """Re-running is the normal case: preprod first, then live, then again after a rebuild."""
    assert "already existed; password re-asserted" in script
    assert "already present; leaving the existing password in place" in script
    assert 'if ! grep -q \'^AUDIT_MAINT_DATABASE_URL=\' .env; then' in script


def test_env_is_backed_up_and_stays_locked_down(script):
    assert "cp .env \".env.bak-audit-" in script
    assert "chmod 600 .env" in script


def test_it_takes_a_lock(script):
    """Two concurrent runs could interleave the password write and the role creation."""
    assert "flock -n 9" in script


def test_it_verifies_and_fails_when_the_boundary_is_not_actually_in_force(script):
    """A script that reports success without checking would be worse than no script: the whole point is
    to be able to answer "is it enforced" with something other than an assumption."""
    verification = script[script.index("== verification"):]
    assert "role_table_grants" in verification
    assert '{"UPDATE", "DELETE", "TRUNCATE"}' in verification
    assert "NOT ENFORCED" in verification
    # And the inverse: a revoke that took INSERT would stop every audit row on the platform.
    assert "BROKEN" in verification and '{"INSERT", "SELECT"}' in verification


def test_the_workflow_is_manual_and_not_attached_to_a_deploy(workflow):
    """A boundary enabled by an unrelated merge is one nobody can say when they enabled, and the evidence
    request is "when did this come into force"."""
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "Deliberately NOT wired into the deploy workflows" in workflow


def test_the_confirmation_is_typed_and_must_match(workflow):
    """The failure mode is picking `live` from the dropdown while meaning `preprod`, which a checkbox does
    nothing about."""
    assert "type: string" in workflow
    assert 'inputs.confirm }}" != "${{ inputs.environment }}"' in workflow
    assert workflow.index("Check the confirmation") < workflow.index("Run via SSM")


def test_each_environment_uses_its_own_role_and_instance(workflow):
    """Sharing either would let a preprod run reach live."""
    for secret in ("LIVE_DEPLOY_ROLE_ARN", "PREPROD_DEPLOY_ROLE_ARN",
                   "LIVE_INSTANCE_ID", "PREPROD_INSTANCE_ID"):
        assert secret in workflow


def test_readiness_is_checked_after_the_privilege_change(workflow):
    """The thing to prove after a revoke is that the application can still write."""
    assert workflow.index("Run via SSM") < workflow.index("Readiness check")
    assert '"status":"ready"' in workflow


def test_the_script_is_delivered_inline_from_the_commit(workflow):
    """So what runs is what is in this commit, not whatever version happens to be on the box."""
    assert "head -n 1 .github/deploy/enable-audit-append-only.sh" in workflow
    assert "jq -Rs" in workflow
