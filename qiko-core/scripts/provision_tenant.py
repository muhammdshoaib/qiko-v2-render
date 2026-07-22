"""Idempotent, transactional tenant provisioning from an operator-owned JSON manifest."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from app.core.config import Environment, Settings
from app.core.db import build_engine, build_sessionmaker
from app.db.provisioning import ProvisioningError, ProvisioningResult, TenantManifest, provision_tenant


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MAX_MANIFEST_BYTES = 1024 * 1024


class ManifestLoadError(Exception):
    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely provision one tenant from an external JSON manifest (dry-run by default)."
    )
    parser.add_argument("--manifest", required=True, help="absolute path to a manifest outside the repository")
    parser.add_argument("--apply", action="store_true", help="apply the planned changes atomically")
    parser.add_argument(
        "--confirm-tenant",
        help="required for live writes and must exactly match the manifest tenant slug",
    )
    parser.add_argument(
        "--reset-existing-passwords",
        action="store_true",
        help="replace existing passwords with unique unrecoverable values; users must use password reset",
    )
    return parser


def _load_manifest(raw_path: str) -> TenantManifest:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise ManifestLoadError("--manifest must be an absolute path")
    try:
        path = candidate.resolve(strict=True)
        if path == _REPOSITORY_ROOT or _REPOSITORY_ROOT in path.parents:
            raise ManifestLoadError("the manifest must be stored outside the repository")
        if not path.is_file():
            raise ManifestLoadError("the manifest path must identify a regular file")
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ManifestLoadError("the manifest exceeds the 1 MiB size limit")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ManifestLoadError:
        raise
    except (OSError, UnicodeError):
        raise ManifestLoadError("the manifest could not be read") from None
    except json.JSONDecodeError:
        raise ManifestLoadError("the manifest is not valid JSON") from None
    try:
        return TenantManifest.model_validate(payload)
    except ValidationError as error:
        locations = sorted({".".join(str(part) for part in item["loc"]) or "manifest" for item in error.errors()})
        raise ManifestLoadError(f"invalid manifest fields: {', '.join(locations)}") from None


def _summary(prefix: str, result: ProvisioningResult) -> str:
    return (
        f"{prefix} tenant={result.tenant} changes={result.changes} "
        f"tenants_created={result.tenants_created} tenants_updated={result.tenants_updated} "
        f"users_created={result.users_created} users_updated={result.users_updated} "
        f"passwords_reset={result.passwords_reset} agents_created={result.agents_created} "
        f"agents_updated={result.agents_updated}"
    )


async def _run(args: argparse.Namespace, settings: Settings, manifest: TenantManifest) -> ProvisioningResult:
    engine = build_engine(settings.database_url)
    try:
        return await provision_tenant(
            build_sessionmaker(engine),
            manifest,
            reset_existing_passwords=args.reset_existing_passwords,
            apply=args.apply,
        )
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = _load_manifest(args.manifest)
        settings = Settings()
        if (
            args.apply
            and settings.environment is Environment.live
            and args.confirm_tenant != manifest.tenant.slug
        ):
            raise ProvisioningError(
                "live writes require --confirm-tenant to exactly match the manifest tenant"
            )
        result = asyncio.run(_run(args, settings, manifest))
    except (ManifestLoadError, ProvisioningError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except Exception:
        print("ERROR: provisioning failed; no changes were committed", file=sys.stderr)
        return 2

    prefix = "DRY_RUN" if not args.apply else "NO_CHANGES" if result.changes == 0 else "APPLIED"
    print(_summary(prefix, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
