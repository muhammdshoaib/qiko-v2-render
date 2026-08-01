import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from app.main import create_app


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPOSITORY_ROOT / "scripts/sync_openapi.py"
OPENAPI_JSON_ARTIFACTS = (
    REPOSITORY_ROOT / "qiko-core/openapi.json",
    REPOSITORY_ROOT / "frontend/packages/api-client/openapi.json",
)
TYPESCRIPT_ARTIFACT = REPOSITORY_ROOT / "frontend/packages/api-client/src/schema.d.ts"
OPENAPI_ARTIFACTS = (*OPENAPI_JSON_ARTIFACTS, TYPESCRIPT_ARTIFACT)


@pytest.fixture
def sync_openapi() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_openapi", SYNC_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def temporary_artifacts(tmp_path: Path) -> tuple[tuple[Path, Path], Path]:
    json_artifacts = (
        tmp_path / "qiko-core/openapi.json",
        tmp_path / "frontend/packages/api-client/openapi.json",
    )
    typescript_artifact = tmp_path / "frontend/packages/api-client/src/schema.d.ts"
    for artifact in (*json_artifacts, typescript_artifact):
        artifact.parent.mkdir(parents=True, exist_ok=True)
    return json_artifacts, typescript_artifact


def configure_temporary_artifacts(
    sync_openapi: ModuleType,
    tmp_path: Path,
    json_artifacts: tuple[Path, Path],
    typescript_artifact: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_openapi, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(sync_openapi, "OPENAPI_JSON_ARTIFACTS", json_artifacts)
    monkeypatch.setattr(sync_openapi, "TYPESCRIPT_ARTIFACT", typescript_artifact)


def test_runtime_openapi_matches_canonical_json_artifacts():
    app = create_app()
    canonical = json.dumps(
        app.openapi(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    assert app.openapi_url == "/openapi.json"
    for artifact in OPENAPI_JSON_ARTIFACTS:
        assert artifact.read_text(encoding="utf-8") == canonical
    assert SYNC_SCRIPT.is_file()


def test_sync_updates_all_three_artifacts_with_canonical_bytes(
    sync_openapi, tmp_path, monkeypatch
):
    json_artifacts, typescript_artifact = temporary_artifacts(tmp_path)
    for artifact in (*json_artifacts, typescript_artifact):
        artifact.write_text("stale", encoding="utf-8")
    configure_temporary_artifacts(
        sync_openapi, tmp_path, json_artifacts, typescript_artifact, monkeypatch
    )
    monkeypatch.setattr(sync_openapi, "_runtime_openapi", lambda: {"z": 1, "a": {"é": True}})

    def generate_typescript():
        assert json_artifacts[0].read_text(encoding="utf-8") == '{"a":{"é":true},"z":1}'
        return "// generated deterministically\nexport interface paths {}\n"

    monkeypatch.setattr(sync_openapi, "_typescript_declarations", generate_typescript)

    assert sync_openapi.main([]) == 0
    assert [artifact.read_text(encoding="utf-8") for artifact in json_artifacts] == [
        '{"a":{"é":true},"z":1}',
        '{"a":{"é":true},"z":1}',
    ]
    assert typescript_artifact.read_text(encoding="utf-8") == (
        "// generated deterministically\nexport interface paths {}\n"
    )


def test_check_reports_all_relative_drift_paths_without_mutation(
    sync_openapi, tmp_path, monkeypatch, capsys
):
    json_artifacts, typescript_artifact = temporary_artifacts(tmp_path)
    artifacts = (*json_artifacts, typescript_artifact)
    for artifact in artifacts:
        artifact.write_text("stale", encoding="utf-8")
    before = [(artifact.read_bytes(), artifact.stat().st_mtime_ns) for artifact in artifacts]
    configure_temporary_artifacts(
        sync_openapi, tmp_path, json_artifacts, typescript_artifact, monkeypatch
    )
    monkeypatch.setattr(sync_openapi, "_runtime_openapi", lambda: {"schema": "must-not-print"})
    monkeypatch.setattr(
        sync_openapi, "_typescript_declarations", lambda: "// schema must not print\n"
    )

    assert sync_openapi.main(["--check"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "qiko-core/openapi.json",
        "frontend/packages/api-client/openapi.json",
        "frontend/packages/api-client/src/schema.d.ts",
    ]
    assert [(artifact.read_bytes(), artifact.stat().st_mtime_ns) for artifact in artifacts] == before


def test_check_detects_stale_typescript_only(sync_openapi, tmp_path, monkeypatch, capsys):
    json_artifacts, typescript_artifact = temporary_artifacts(tmp_path)
    for artifact in json_artifacts:
        artifact.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    typescript_artifact.write_text("stale typescript", encoding="utf-8")
    before = [(artifact.read_bytes(), artifact.stat().st_mtime_ns) for artifact in (*json_artifacts, typescript_artifact)]
    configure_temporary_artifacts(
        sync_openapi, tmp_path, json_artifacts, typescript_artifact, monkeypatch
    )
    monkeypatch.setattr(sync_openapi, "_runtime_openapi", lambda: {"openapi": "3.1.0"})
    monkeypatch.setattr(sync_openapi, "_typescript_declarations", lambda: "generated typescript\n")

    assert sync_openapi.main(["--check"]) == 1
    assert capsys.readouterr().out == "frontend/packages/api-client/src/schema.d.ts\n"
    assert [
        (artifact.read_bytes(), artifact.stat().st_mtime_ns)
        for artifact in (*json_artifacts, typescript_artifact)
    ] == before


def test_atomic_replace_failure_preserves_old_file_and_cleans_temporary_file(
    sync_openapi, tmp_path, monkeypatch
):
    artifact = tmp_path / "openapi.json"
    artifact.write_text("old", encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(sync_openapi.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replacement failure"):
        sync_openapi._atomic_write(artifact, "new")

    assert artifact.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.iterdir()) == [artifact]


def test_runtime_generation_is_isolated_from_hostile_environment_and_cwd_dotenv(tmp_path):
    (tmp_path / ".env").write_text("ENVIRONMENT=live\nPUBLIC_CHAT_ENABLED=true\n", encoding="utf-8")
    helper = f"""
import hashlib
import importlib.util
import json
import sys
spec = importlib.util.spec_from_file_location("isolated_sync_openapi", {str(SYNC_SCRIPT)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
schema = module._runtime_openapi()
canonical = json.dumps(schema, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
print(json.dumps({{"app_imported": any(name == "app" or name.startswith("app.") for name in sys.modules), "sha256": hashlib.sha256(canonical).hexdigest()}}, sort_keys=True))
"""
    environment = {
        "ENVIRONMENT": "live",
        "PATH": os.defpath,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(tmp_path / "hostile-python-path"),
    }

    result = subprocess.run(
        [sys.executable, "-c", helper],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    evidence = json.loads(result.stdout)

    assert evidence == {
        "app_imported": False,
        "sha256": hashlib.sha256(OPENAPI_JSON_ARTIFACTS[0].read_bytes()).hexdigest(),
    }


def test_runtime_generation_failure_is_sanitized(sync_openapi, monkeypatch):
    failure = subprocess.CompletedProcess(
        args=["python"],
        returncode=1,
        stdout='{"schema":"must-not-leak"}',
        stderr="HOST_SECRET=must-not-leak",
    )
    monkeypatch.setattr(sync_openapi.subprocess, "run", lambda *args, **kwargs: failure)

    with pytest.raises(RuntimeError) as error:
        sync_openapi._runtime_openapi()

    assert str(error.value) == "OpenAPI generation failed in isolated process"


def test_typescript_generation_uses_external_temporary_directories_and_cleans_success(
    sync_openapi, monkeypatch
):
    success = subprocess.CompletedProcess(
        args=["pnpm"],
        returncode=0,
        stdout="/**\n * This file was auto-generated by openapi-typescript.\n */\n",
        stderr="",
    )
    observed_paths = []
    environment_paths = (
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "NPM_CONFIG_CACHE",
        "NPM_CONFIG_STORE_DIR",
        "PNPM_HOME",
        "PNPM_STORE_DIR",
        "TMPDIR",
    )
    monkeypatch.setattr(
        sync_openapi,
        "_find_executable",
        lambda name: f"/trusted-tools/{name}",
    )

    def generate(*args, **kwargs):
        repository = sync_openapi.REPOSITORY_ROOT.resolve()
        for name in environment_paths:
            path = Path(kwargs["env"][name])
            assert path.exists()
            assert not path.resolve().is_relative_to(repository)
            observed_paths.append(path)
        cache_marker = Path(kwargs["env"]["XDG_CACHE_HOME"]) / "generator-cache"
        cache_marker.write_text("temporary", encoding="utf-8")
        return success

    monkeypatch.setattr(sync_openapi.subprocess, "run", generate)

    assert sync_openapi._typescript_declarations() == success.stdout
    assert observed_paths
    assert all(not path.exists() for path in observed_paths)


def test_typescript_generation_failure_is_sanitized_and_uses_fixed_arguments(
    sync_openapi, monkeypatch
):
    failure = subprocess.CompletedProcess(
        args=["pnpm"],
        returncode=1,
        stdout="generated schema must not leak",
        stderr="NPM_TOKEN=must-not-leak",
    )
    calls = []
    temporary_homes = []
    monkeypatch.setenv("ENVIRONMENT", "live")
    monkeypatch.setattr(
        sync_openapi,
        "_find_executable",
        lambda name: f"/trusted-tools/{name}",
    )

    def fail_generation(*args, **kwargs):
        home = Path(kwargs["env"]["HOME"])
        assert home.exists()
        temporary_homes.append(home)
        calls.append((args, kwargs))
        return failure

    monkeypatch.setattr(sync_openapi.subprocess, "run", fail_generation)

    with pytest.raises(RuntimeError) as error:
        sync_openapi._typescript_declarations()

    assert str(error.value) == "TypeScript generation failed"
    args, kwargs = calls[0]
    assert args[0] == [
        "/trusted-tools/pnpm",
        "exec",
        "openapi-typescript",
        str(sync_openapi.CORE_ROOT / "openapi.json"),
    ]
    assert kwargs["cwd"] == sync_openapi.API_CLIENT_ROOT
    assert kwargs["timeout"] == 60
    assert kwargs["env"]["COREPACK_ENABLE_NETWORK"] == "0"
    assert kwargs["env"]["NPM_CONFIG_OFFLINE"] == "true"
    assert "ENVIRONMENT" not in kwargs["env"]
    assert "shell" not in kwargs
    assert temporary_homes and all(not path.exists() for path in temporary_homes)


def test_typescript_generation_timeout_cleans_temporary_home(sync_openapi, monkeypatch):
    temporary_homes = []
    monkeypatch.setattr(
        sync_openapi,
        "_find_executable",
        lambda name: f"/trusted-tools/{name}",
    )

    def time_out(*args, **kwargs):
        home = Path(kwargs["env"]["HOME"])
        assert home.exists()
        temporary_homes.append(home)
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(sync_openapi.subprocess, "run", time_out)

    with pytest.raises(RuntimeError, match="^TypeScript generation failed$"):
        sync_openapi._typescript_declarations()

    assert temporary_homes and all(not path.exists() for path in temporary_homes)


def test_tracked_artifact_check_preserves_bytes_and_mtimes(sync_openapi, capsys):
    before = [(artifact.read_bytes(), artifact.stat().st_mtime_ns) for artifact in OPENAPI_ARTIFACTS]

    assert sync_openapi.main(["--check"]) == 0

    assert capsys.readouterr().out == ""
    assert [(artifact.read_bytes(), artifact.stat().st_mtime_ns) for artifact in OPENAPI_ARTIFACTS] == before


def test_api_client_readme_documents_single_file_based_command():
    readme = (REPOSITORY_ROOT / "frontend/packages/api-client/README.md").read_text(encoding="utf-8")

    assert "scripts/sync_openapi.py" in readme
    assert "OPENAPI_URL" not in readme
    assert "running backend" not in readme


def test_ci_filters_and_local_caddy_validation_cover_task_contracts():
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    lines = workflow.splitlines()
    for filter_name in ("backend", "frontend", "compose"):
        start = lines.index(f"            {filter_name}:") + 1
        paths = []
        for line in lines[start:]:
            if not line.startswith("              - "):
                break
            paths.append(line.strip())
        assert "- '.github/workflows/ci.yml'" in paths

    assert (
        'docker run --rm -e CREATOR_UPSTREAM=creator:3000 -e ADMIN_UPSTREAM=admin:3001 '
        '-v "$PWD/Caddyfile.dev:/etc/caddy/Caddyfile:ro" caddy:2 caddy validate '
        '--config /etc/caddy/Caddyfile'
    ) in workflow
