"""Development-only tenant owner and platform Admin bootstrap."""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from app.core.config import Environment, Settings
from app.core.db import build_engine, build_sessionmaker
from app.db.dev_bootstrap import DevBootstrapError, DevBootstrapResult, bootstrap_dev_admin


class CliUsageError(Exception):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError("invalid command arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        description="Bootstrap one local development Admin identity.",
    )
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password-stdin", action="store_true")
    parser.add_argument("--reset-password", action="store_true")
    return parser


def _read_password() -> str:
    try:
        raw = sys.stdin.read(258)
    except (OSError, UnicodeError):
        raise CliUsageError("password could not be read from stdin") from None
    if raw.endswith("\r\n"):
        raw = raw[:-2]
    elif raw.endswith(("\r", "\n")):
        raw = raw[:-1]
    if (
        len(raw) < 8
        or len(raw) > 256
        or not raw.strip()
        or any(ord(character) < 32 for character in raw)
    ):
        raise CliUsageError("password must contain between 8 and 256 characters")
    return raw


async def _run(
    args: argparse.Namespace,
    settings: Settings,
    password: str,
) -> DevBootstrapResult:
    engine = build_engine(settings.database_url)
    try:
        return await bootstrap_dev_admin(
            build_sessionmaker(engine),
            args.tenant,
            args.display_name,
            args.email,
            password,
            reset_password=args.reset_password,
        )
    finally:
        await engine.dispose()


def _summary(result: DevBootstrapResult) -> str:
    prefix = "NO_CHANGES" if result.changes == 0 else "BOOTSTRAP_APPLIED"
    return (
        f"{prefix} changes={result.changes} "
        f"tenant_created={int(result.tenant_created)} "
        f"tenant_updated={int(result.tenant_updated)} "
        f"user_created={int(result.user_created)} "
        f"password_reset={int(result.password_reset)} "
        f"owner_granted={int(result.owner_granted)} "
        f"super_admin_granted={int(result.super_admin_granted)} "
        f"user_email_normalized={int(result.user_email_normalized)} "
        f"admin_email_normalized={int(result.admin_email_normalized)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    try:
        if any(value == "--password" or value.startswith("--password=") for value in raw_argv):
            raise CliUsageError("password arguments are not supported; use --password-stdin")
        args = _parser().parse_args(raw_argv)
        settings = Settings(_env_file=None)
        if settings.environment is not Environment.dev:
            raise DevBootstrapError("bootstrap is available only when ENVIRONMENT=dev")
        if settings.use_db_stores is not True:
            raise DevBootstrapError("bootstrap requires USE_DB_STORES=true")
        if not args.password_stdin:
            raise CliUsageError("--password-stdin is required")
        password = _read_password()
        result = asyncio.run(_run(args, settings, password))
    except (CliUsageError, DevBootstrapError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except SystemExit as error:
        return int(error.code)
    except Exception:
        print(
            "ERROR: development bootstrap did not complete; verify local database state",
            file=sys.stderr,
        )
        return 2

    print(_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
