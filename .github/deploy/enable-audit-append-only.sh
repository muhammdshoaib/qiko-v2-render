#!/bin/bash
# Turns on the append-only boundary for audit_events. Runs ON the target box via SSM Run Command,
# invoked by .github/workflows/enable-audit-append-only.yml.
#
# WHY THIS IS A SCRIPT IN THE REPO AND NOT SOMETHING SOMEBODY TYPES.
#
# It is a four-step privilege change with an ordering constraint: the maintenance role has to exist and
# the worker has to be able to reach it BEFORE the application role loses UPDATE and DELETE, or retention
# stops working and the audit trail silently accumulates personal data past its stated policy. Typed by
# hand, in two environments, weeks apart, that order is the thing that gets forgotten. Here it is
# reviewable in a diff, identical on preprod and live, and re-runnable.
#
# It also means nobody has to hold the database password. The box already has it in .env; this script
# reads it there and never prints it.
#
# IDEMPOTENT. Re-running is the normal case: the role is created only if absent, the password is set only
# if the URL is not already in .env, and migration 0039 revokes only what is still granted. A second run
# reports the same end state rather than failing.
set -uo pipefail
umask 077

# Matches redeploy-*.sh. Wrong here and every step would run against a directory with no .env.
BASE="${QIKO_BASE:-/opt/docker/qiko}"
COMPOSE_FILES="${QIKO_COMPOSE_FILES:?set QIKO_COMPOSE_FILES}"
ROLE="qiko_audit_maint"

exec 9>"/var/lock/qiko-audit-append-only.lock"
if ! flock -n 9; then
  echo "FATAL: another run is already in progress" >&2
  exit 1
fi

cd "$BASE/platform" || { echo "FATAL: $BASE/platform missing" >&2; exit 1; }
[ -f .env ] && [ ! -L .env ] || { echo "FATAL: .env must be a regular file" >&2; exit 1; }
C="docker compose $COMPOSE_FILES"

# The application URL is the source of truth for host, port and database name. Deriving the maintenance
# URL from it means the two cannot drift, and a typo in a hand-written URL cannot point the retention job
# at the wrong database.
APP_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"
[ -n "$APP_URL" ] || { echo "FATAL: DATABASE_URL not found in .env" >&2; exit 1; }

# Everything after the credentials: @host:port/dbname
TAIL="${APP_URL#*@}"
[ "$TAIL" != "$APP_URL" ] || { echo "FATAL: DATABASE_URL has no credentials section" >&2; exit 1; }
SCHEME="${APP_URL%%://*}"

echo "== step 1: ensure the $ROLE role exists =="
if grep -q '^AUDIT_MAINT_DATABASE_URL=' .env; then
  echo "AUDIT_MAINT_DATABASE_URL already present; leaving the existing password in place"
  MAINT_URL="$(grep -m1 '^AUDIT_MAINT_DATABASE_URL=' .env | cut -d= -f2-)"
  # Extract just the password so the role can be re-synced if it was dropped by hand.
  CREDS="${MAINT_URL#*://}"; CREDS="${CREDS%%@*}"
  MAINT_PASSWORD="${CREDS#*:}"
else
  # Generated on the box, so it never exists in CI logs, a GitHub secret, or an agent transcript.
  MAINT_PASSWORD="$(openssl rand -base64 33 | tr -d '/+=' | cut -c1-40)"
  MAINT_URL="${SCHEME}://${ROLE}:${MAINT_PASSWORD}@${TAIL}"
fi

# psql through the app container, so this needs no client installed on the host. The password reaches
# psql as a bound parameter for the role name and inside a DO block for the secret, never on a command
# line where it would land in the process table.
if ! $C run --rm --no-deps \
  -e PGPASSWORD_NEW="$MAINT_PASSWORD" -e ROLE_NAME="$ROLE" qiko-core \
  python - <<'PY'
import asyncio
import os

from sqlalchemy import text

from app.core.db import build_engine


async def main() -> int:
    role = os.environ["ROLE_NAME"]
    secret = os.environ["PGPASSWORD_NEW"]
    engine = build_engine()
    async with engine.begin() as conn:
        exists = (await conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role})).scalar()
        # CREATE ROLE cannot take a bound parameter for the password, so it is quoted through the
        # server's own literal quoting rather than by string formatting here.
        literal = (await conn.execute(text("SELECT quote_literal(:s)"), {"s": secret})).scalar()
        ident = (await conn.execute(text("SELECT quote_ident(:r)"), {"r": role})).scalar()
        if exists:
            # Re-assert the password so a re-run repairs a mismatch between .env and the database.
            await conn.execute(text(f"ALTER ROLE {ident} WITH LOGIN PASSWORD {literal}"))
            print(f"role {role} already existed; password re-asserted")
        else:
            await conn.execute(text(f"CREATE ROLE {ident} WITH LOGIN PASSWORD {literal}"))
            print(f"role {role} created")
        # CONNECT is separate from table grants and is easy to forget; without it the worker fails at
        # the handshake rather than at the query, which reads as an outage instead of a missing grant.
        db = (await conn.execute(text("SELECT quote_ident(current_database())"))).scalar()
        await conn.execute(text(f"GRANT CONNECT ON DATABASE {db} TO {ident}"))
    await engine.dispose()
    return 0


raise SystemExit(asyncio.run(main()))
PY
then
  echo "FATAL: could not create or update the $ROLE role" >&2
  exit 1
fi

echo "== step 2: put the maintenance URL in .env, BEFORE the revoke =="
if ! grep -q '^AUDIT_MAINT_DATABASE_URL=' .env; then
  cp .env ".env.bak-audit-$(date -u +%Y%m%dT%H%M%SZ)" || {
    echo "FATAL: could not back up .env" >&2; exit 1; }
  printf 'AUDIT_MAINT_DATABASE_URL=%s\n' "$MAINT_URL" >> .env
  echo "AUDIT_MAINT_DATABASE_URL appended"
fi
chmod 600 .env

echo "== step 3: restart the worker so it picks the maintenance connection up =="
# Before the migration, so retention never has a window where it lacks the grant it is about to need.
if ! $C up -d --no-deps worker; then
  echo "FATAL: worker restart failed; not proceeding to the revoke" >&2
  exit 1
fi

echo "== step 4: run migrations, which now find the role and perform the revoke =="
if ! $C run --rm --no-deps qiko-core alembic upgrade head; then
  echo "FATAL: alembic upgrade failed; the revoke may not have been applied" >&2
  exit 1
fi

echo "== verification: the grants as the database now reports them =="
# This output is the evidence an auditor asks for, so it is printed rather than merely checked.
$C run --rm --no-deps qiko-core python - <<'PY'
import asyncio

from sqlalchemy import text

from app.core.db import build_engine


async def main() -> int:
    engine = build_engine()
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT grantee, string_agg(privilege_type, ',' ORDER BY privilege_type)
            FROM information_schema.role_table_grants
            WHERE table_name = 'audit_events'
            GROUP BY grantee ORDER BY grantee
        """))).all()
        for grantee, privileges in rows:
            print(f"  {grantee}: {privileges}")

        app_role = (await conn.execute(text("SELECT current_user"))).scalar()
        app_privileges = {p for g, privs in rows if g == app_role for p in privs.split(",")}
        forbidden = app_privileges & {"UPDATE", "DELETE", "TRUNCATE"}
        required = {"INSERT", "SELECT"} - app_privileges
        if forbidden:
            print(f"NOT ENFORCED: {app_role} still holds {sorted(forbidden)}")
            return 1
        if required:
            print(f"BROKEN: {app_role} is missing {sorted(required)}")
            return 1
        print(f"ENFORCED: {app_role} can INSERT and SELECT only")
    await engine.dispose()
    return 0


raise SystemExit(asyncio.run(main()))
PY
