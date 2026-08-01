#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPOSITORY_ROOT / "qiko-core"
API_CLIENT_ROOT = REPOSITORY_ROOT / "frontend/packages/api-client"
OPENAPI_JSON_ARTIFACTS = (
    CORE_ROOT / "openapi.json",
    API_CLIENT_ROOT / "openapi.json",
)
TYPESCRIPT_ARTIFACT = API_CLIENT_ROOT / "src/schema.d.ts"
_GENERATION_FAILURE = "OpenAPI generation failed in isolated process"
_TYPESCRIPT_FAILURE = "TypeScript generation failed"


def _child_environment() -> dict[str, str]:
    environment = {
        "PATH": os.defpath,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    for name in ("SYSTEMROOT", "WINDIR"):
        if value := os.environ.get(name):
            environment[name] = value
    return environment


def _runtime_openapi_in_child() -> dict[str, Any]:
    sys.path.insert(0, str(CORE_ROOT))
    from app.core import config

    settings = config.Settings.model_validate({})

    def default_settings():
        return settings

    config.get_settings = default_settings

    from app.main import create_app

    return create_app().openapi()


def _runtime_openapi() -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--_emit-runtime"],
            env=_child_environment(),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise RuntimeError(_GENERATION_FAILURE) from None
    if result.returncode != 0:
        raise RuntimeError(_GENERATION_FAILURE)
    try:
        schema = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        raise RuntimeError(_GENERATION_FAILURE) from None
    if not isinstance(schema, dict):
        raise RuntimeError(_GENERATION_FAILURE)
    return schema


def _canonical_json(schema: dict[str, Any]) -> str:
    return json.dumps(
        schema,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _find_executable(name: str) -> str:
    candidate = shutil.which(name)
    if candidate is None:
        raise RuntimeError(_TYPESCRIPT_FAILURE)
    path = Path(candidate).absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(_TYPESCRIPT_FAILURE)
    return str(path)


def _typescript_environment(pnpm: str, node: str, temporary_root: Path) -> dict[str, str]:
    directories = {
        "HOME": temporary_root / "home",
        "NPM_CONFIG_CACHE": temporary_root / "npm-cache",
        "NPM_CONFIG_PREFIX": temporary_root / "npm-prefix",
        "NPM_CONFIG_STATE_DIR": temporary_root / "pnpm-state",
        "NPM_CONFIG_STORE_DIR": temporary_root / "pnpm-store",
        "PNPM_HOME": temporary_root / "pnpm-home",
        "PNPM_STORE_DIR": temporary_root / "pnpm-store",
        "TMPDIR": temporary_root / "tmp",
        "XDG_CACHE_HOME": temporary_root / "cache",
        "XDG_CONFIG_HOME": temporary_root / "config",
        "XDG_DATA_HOME": temporary_root / "data",
        "XDG_STATE_HOME": temporary_root / "state",
    }
    for directory in set(directories.values()):
        directory.mkdir(parents=True)
    environment = {
        "PATH": os.pathsep.join(
            dict.fromkeys((str(Path(pnpm).parent), str(Path(node).parent), os.defpath))
        ),
        "CI": "1",
        "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
        "COREPACK_ENABLE_NETWORK": "0",
        "FORCE_COLOR": "0",
        "NO_COLOR": "1",
        "NPM_CONFIG_OFFLINE": "true",
        "NPM_CONFIG_USERCONFIG": os.devnull,
        **{name: str(path) for name, path in directories.items()},
    }
    environment["TEMP"] = environment["TMPDIR"]
    environment["TMP"] = environment["TMPDIR"]
    for name in ("SYSTEMROOT", "WINDIR"):
        if value := os.environ.get(name):
            environment[name] = value
    return environment


def _typescript_declarations() -> str:
    pnpm = _find_executable("pnpm")
    node = _find_executable("node")
    repository = REPOSITORY_ROOT.resolve()
    try:
        with tempfile.TemporaryDirectory(
            prefix="qiko-openapi-tools-", dir=repository.parent
        ) as temporary_name:
            temporary_root = Path(temporary_name).resolve()
            if temporary_root.is_relative_to(repository):
                raise RuntimeError(_TYPESCRIPT_FAILURE)
            result = subprocess.run(
                [
                    pnpm,
                    "exec",
                    "openapi-typescript",
                    str(CORE_ROOT / "openapi.json"),
                ],
                cwd=API_CLIENT_ROOT,
                env=_typescript_environment(pnpm, node, temporary_root),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise RuntimeError(_TYPESCRIPT_FAILURE) from None
    if result.returncode != 0 or not result.stdout.startswith(
        "/**\n * This file was auto-generated by openapi-typescript."
    ):
        raise RuntimeError(_TYPESCRIPT_FAILURE)
    return result.stdout


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        os.chmod(temporary_path, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise


def _differs(path: Path, content: str) -> bool:
    return not path.exists() or path.read_text(encoding="utf-8") != content


def _check_artifacts(json_content: str, typescript_content: str) -> list[Path]:
    expected = [
        *((path, json_content) for path in OPENAPI_JSON_ARTIFACTS),
        (TYPESCRIPT_ARTIFACT, typescript_content),
    ]
    return [path for path, content in expected if _differs(path, content)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronize checked-in OpenAPI artifacts.")
    parser.add_argument("--check", action="store_true", help="Report drift without writing files.")
    parser.add_argument("--_emit-runtime", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)

    if arguments._emit_runtime:
        sys.stdout.write(_canonical_json(_runtime_openapi_in_child()))
        return 0

    json_content = _canonical_json(_runtime_openapi())
    if arguments.check:
        typescript_content = _typescript_declarations()
        drifted = _check_artifacts(json_content, typescript_content)
        for path in drifted:
            print(path.relative_to(REPOSITORY_ROOT).as_posix())
        return int(bool(drifted))

    for path in OPENAPI_JSON_ARTIFACTS:
        if _differs(path, json_content):
            _atomic_write(path, json_content)
    typescript_content = _typescript_declarations()
    if _differs(TYPESCRIPT_ARTIFACT, typescript_content):
        _atomic_write(TYPESCRIPT_ARTIFACT, typescript_content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
