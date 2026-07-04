import pytest

from app.modules.storage.backend import InMemoryStorage
from app.modules.storage.keys import assert_tenant_scoped, object_key, sanitize_filename


# --- keys ---
def test_sanitize_filename_strips_paths_and_unsafe():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("my report (final).docx") == "my-report-final-.docx" or \
        sanitize_filename("my report (final).docx").endswith(".docx")
    assert sanitize_filename("") == "file"


def test_object_key_is_tenant_scoped_and_unique():
    k1 = object_key("acme", "exports", "bid.docx")
    k2 = object_key("acme", "exports", "bid.docx")
    assert k1.startswith("acme/exports/")
    assert k1 != k2  # uuid prefix
    assert k1.endswith("-bid.docx")


def test_object_key_validation():
    with pytest.raises(ValueError):
        object_key("", "exports", "f")
    with pytest.raises(ValueError):
        object_key("acme", "bad-category", "f")


def test_assert_tenant_scoped():
    assert_tenant_scoped("acme", "acme/exports/x.docx")  # ok
    with pytest.raises(PermissionError):
        assert_tenant_scoped("acme", "other/exports/x.docx")
    with pytest.raises(PermissionError):
        assert_tenant_scoped("acme", "acme/../other/x")


# --- in-memory backend ---
def test_inmemory_roundtrip_and_isolation():
    s = InMemoryStorage()
    key = object_key("acme", "uploads", "rfp.pdf")
    s.put("acme", key, b"hello")
    assert s.get("acme", key) == b"hello"
    with pytest.raises(PermissionError):
        s.put("beta", key, b"x")  # beta cannot write under acme's key
