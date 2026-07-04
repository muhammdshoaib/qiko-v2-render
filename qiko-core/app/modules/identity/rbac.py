"""Role-based access control. Roles are ordered; a higher role satisfies a lower requirement."""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    viewer = "viewer"
    editor = "editor"
    admin = "admin"
    owner = "owner"


_ORDER = {Role.viewer: 0, Role.editor: 1, Role.admin: 2, Role.owner: 3}


def role_allows(actual: Role | str, required: Role | str) -> bool:
    """True if `actual` role meets or exceeds `required`."""
    a, r = Role(actual), Role(required)
    return _ORDER[a] >= _ORDER[r]
