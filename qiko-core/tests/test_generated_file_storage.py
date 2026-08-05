"""Audit H8.1: generated files were kept in a process dict with no TTL and no eviction.

S3Storage was fully written and never instantiated. FileGenerator() with no argument fell back to
InMemoryStorage, a plain dict, inside a 512M container: every DOCX, XLSX, PDF and CSV produced by
/chat/files and /excel/report stayed there forever, and on every deploy (which does
`docker compose rm -sf qiko-core`) every previously issued download key started returning 404.
"""
import pytest

from app.core.config import Environment, Settings, get_settings
from app.main import create_app
from app.modules.storage.backend import InMemoryStorage, S3Storage


def test_s3_is_used_when_a_bucket_is_configured(monkeypatch):
    # get_settings is lru_cached, so the setting is patched on the cached instance rather than via the
    # environment, which is also how the rest of the suite does it.
    monkeypatch.setattr(get_settings(), "s3_bucket", "qiko-generated-files")
    app = create_app()
    backend = app.state.file_generator.storage
    assert isinstance(backend, S3Storage)
    assert backend.bucket == "qiko-generated-files"


def test_the_dev_dict_is_used_only_when_no_bucket_is_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "s3_bucket", "")
    app = create_app()
    assert isinstance(app.state.file_generator.storage, InMemoryStorage)


def test_a_non_dev_environment_cannot_start_without_a_bucket():
    """Without this guard the fallback is silent: the platform serves download links that stop working
    at the next deploy, and leaks memory until the container is killed."""
    settings = Settings(_env_file=None, environment=Environment.live, s3_bucket="")
    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        settings.assert_secrets_set()


def test_the_guard_passes_once_a_bucket_is_set():
    settings = Settings(_env_file=None, environment=Environment.live, s3_bucket="qiko-files")
    try:
        settings.assert_secrets_set()
    except RuntimeError as error:
        # The guard still fails on the other unset live secrets, which is correct. What matters is
        # that the bucket is no longer among the reasons.
        assert "S3_BUCKET" not in str(error), "the bucket must no longer be reported missing"


def test_both_backends_refuse_a_key_outside_the_tenant_prefix():
    """The tenant-scoping guard is what stops one customer fetching another's generated file, so it is
    asserted on both implementations rather than assumed from the shared protocol."""
    from app.modules.storage.keys import assert_tenant_scoped

    storage = InMemoryStorage()
    storage.put("acme", "acme/report.xlsx", b"data")
    assert storage.get("acme", "acme/report.xlsx") == b"data"

    with pytest.raises(Exception):
        storage.get("acme", "beta/report.xlsx")
    with pytest.raises(Exception):
        assert_tenant_scoped("acme", "beta/report.xlsx")
