"""Operator CLI to provision a platform admin in preprod or live (QIK-513).

Why this exists
---------------
`POST /admin/org/bootstrap` is deliberately dev-only: outside dev, letting the first caller to reach
an endpoint appoint themselves is a self-escalation race. Until now that left NO production path at
all, so the only way to create a platform admin in preprod or live was a manual `platform_admins`
row insert. This is that path, with the same safety shape as `scripts/provision_tenant.py`.

Usage (run inside the qiko-core container so settings and credentials resolve):

    # dry run by default: reports the plan, writes nothing
    python scripts/provision_platform_admin.py --email ops@example.com --role super_admin

    # apply; on live the email must be repeated with --confirm-email
    python scripts/provision_platform_admin.py --email ops@example.com --role super_admin \
        --apply --confirm-email ops@example.com

    # grant a narrow capability set instead of the role default
    python scripts/provision_platform_admin.py --email support@example.com --role viewer \
        --capabilities view_customers,manage_workers --apply --confirm-email support@example.com

Every write is audited in `platform_admin_audit` with `changed_by_email` recording the operator
identity passed via `--actor` (defaults to `operator-cli`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import Environment, Settings  # noqa: E402
from app.db.stores import SqlAdminOrgStore  # noqa: E402
from app.modules.identity.admin_rbac import (  # noqa: E402
    AdminRole,
    Capability,
    effective_capabilities,
    parse_capabilities,
)


class ProvisioningError(Exception):
    """A fail-closed precondition error safe to show to an operator."""


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str):  # noqa: ANN201 - argparse contract
        raise ProvisioningError("invalid command arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(description="Provision a platform admin.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=[role.value for role in AdminRole])
    parser.add_argument("--capabilities", default=None,
                        help="comma-separated capability names; omit to use the role default")
    parser.add_argument("--reason", default="provisioned by operator CLI")
    parser.add_argument("--actor", default="operator-cli",
                        help="recorded as changed_by_email in the audit trail")
    parser.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    parser.add_argument("--confirm-email", default=None,
                        help="required on live: must repeat --email exactly")
    return parser


def _normalise_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email.strip("@") or len(email) > 320 or any(c.isspace() for c in email):
        raise ProvisioningError("email must be a single valid address")
    return email


def _parse_capability_arg(raw: str | None) -> frozenset[Capability] | None:
    if raw is None:
        return None
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise ProvisioningError("--capabilities was given but empty")
    try:
        return parse_capabilities(names)
    except ValueError as error:
        known = ", ".join(sorted(c.value for c in Capability))
        raise ProvisioningError(f"unknown capability; known values are: {known}") from error


async def _run(args: argparse.Namespace, settings: Settings) -> tuple[str, dict]:
    email = _normalise_email(args.email)
    role = AdminRole(args.role)
    capabilities = _parse_capability_arg(args.capabilities)
    resolved = sorted(c.value for c in effective_capabilities(role, capabilities))

    engine = create_async_engine(settings.database_url)
    try:
        store = SqlAdminOrgStore(async_sessionmaker(engine, expire_on_commit=False))
        existing = await store.get_identity(email)
        plan = {
            "email": email,
            "role": role.value,
            "capabilities": resolved,
            "previous_role": existing.role.value if existing else None,
        }
        if not args.apply:
            return "DRY_RUN", plan
        if existing and existing.role is role and sorted(
                c.value for c in existing.capabilities) == resolved:
            return "NO_CHANGES", plan
        await store.grant(email, role, capabilities,
                          changed_by_email=args.actor, reason=args.reason)
        return "APPLIED", plan
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        settings = Settings()
        if settings.use_db_stores is not True:
            raise ProvisioningError("provisioning requires USE_DB_STORES=true")
        if args.apply and settings.environment is Environment.live:
            # Same guard as provision_tenant: a live write must be typed out twice.
            if args.confirm_email is None or _normalise_email(args.confirm_email) != _normalise_email(args.email):
                raise ProvisioningError(
                    "live writes require --confirm-email to exactly match --email")
        prefix, plan = asyncio.run(_run(args, settings))
    except ProvisioningError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except Exception:
        # Never leak a connection string or driver detail to an operator's terminal.
        print("ERROR: provisioning failed; no changes were committed", file=sys.stderr)
        return 2

    print(f"{prefix} email={plan['email']} role={plan['role']} "
          f"previous_role={plan['previous_role']} capabilities={','.join(plan['capabilities'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
