"""Tenant-scoped object keys. Every object lives under its tenant prefix, and filenames are
sanitised so a caller can never traverse out of their tenant's namespace."""
from __future__ import annotations

import posixpath
import re
import uuid

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_CATEGORIES = {"uploads", "exports", "reports"}


def sanitize_filename(filename: str) -> str:
    # Drop any path components, then replace unsafe chars.
    base = posixpath.basename((filename or "").replace("\\", "/")).lstrip(".")
    cleaned = _SAFE.sub("-", base).strip("-")
    return cleaned or "file"


def object_key(tenant: str, category: str, filename: str) -> str:
    if not tenant:
        raise ValueError("tenant is required")
    if category not in _CATEGORIES:
        raise ValueError(f"category must be one of {sorted(_CATEGORIES)}")
    return f"{tenant}/{category}/{uuid.uuid4().hex}-{sanitize_filename(filename)}"


def assert_tenant_scoped(tenant: str, key: str) -> None:
    """Guard before any read/write: the key must live under this tenant's prefix."""
    prefix = f"{tenant}/"
    normalized = posixpath.normpath(key)
    if not key.startswith(prefix) or normalized.startswith("..") or "/../" in key:
        raise PermissionError("object key is outside the tenant namespace")
