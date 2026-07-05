"""Admin-organisation RBAC - DISTINCT from the product tenant RBAC (owner/admin/editor/viewer).

Two roles: super_admin (manages admins + everything) and viewer (read-all, no mutations). Only a
super_admin may invite admins or assign roles.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

import jwt

from app.core.config import get_settings

_ALGO = "HS256"


class AdminRole(str, Enum):
    super_admin = "super_admin"
    viewer = "viewer"


def can_invite_admins(role: AdminRole) -> bool:
    return role is AdminRole.super_admin


def can_assign_role(role: AdminRole) -> bool:
    return role is AdminRole.super_admin


def can_manage_admins(role: AdminRole) -> bool:
    return role is AdminRole.super_admin


class AdminAuthzError(Exception):
    pass


@dataclass
class AdminOrg:
    _admins: dict[str, AdminRole] = field(default_factory=dict)

    def bootstrap_super_admin(self, email: str) -> None:
        self._admins[email.lower()] = AdminRole.super_admin

    def invite(self, actor: str, email: str, role: AdminRole) -> str:
        if self._admins.get(actor.lower()) is not AdminRole.super_admin:
            raise AdminAuthzError("only a super_admin can invite admins")
        return jwt.encode({"email": email.lower(), "role": role.value, "exp": int(time.time()) + 604800},
                          get_settings().session_secret, algorithm=_ALGO)

    def accept(self, token: str) -> AdminRole:
        try:
            data = jwt.decode(token, get_settings().session_secret, algorithms=[_ALGO])
        except jwt.PyJWTError as e:
            raise AdminAuthzError("invalid or expired invite") from e
        role = AdminRole(data["role"])
        self._admins[data["email"]] = role
        return role

    def remove(self, actor: str, email: str) -> None:
        if self._admins.get(actor.lower()) is not AdminRole.super_admin:
            raise AdminAuthzError("only a super_admin can remove admins")
        self._admins.pop(email.lower(), None)

    def role_of(self, email: str) -> AdminRole | None:
        return self._admins.get(email.lower())

    def is_empty(self) -> bool:
        return not self._admins
