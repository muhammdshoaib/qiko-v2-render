"""Admin-organisation RBAC - DISTINCT from the product tenant RBAC (owner/admin/editor/viewer).

Two roles: super_admin (manages admins + everything) and viewer (read-all, no mutations). Only a
super_admin may invite admins or assign roles.

Async + store-backed (Protocol + InMemory/Sql implementations, same pattern as Agents/RfpPacks):
this registry used to be a plain in-memory dict, wiped on every redeploy, which made
/admin/org/bootstrap a "first caller after a redeploy wins" race and forced manually
re-bootstrapping a platform admin after every deploy (SCRUM-80).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

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


class AdminOrgStore(Protocol):
    async def get(self, email: str) -> AdminRole | None: ...
    async def set(self, email: str, role: AdminRole) -> None: ...
    async def delete(self, email: str) -> None: ...
    async def is_empty(self) -> bool: ...


@dataclass
class InMemoryAdminOrgStore:
    _admins: dict[str, AdminRole] = field(default_factory=dict)

    async def get(self, email: str) -> AdminRole | None:
        return self._admins.get(email.lower())

    async def set(self, email: str, role: AdminRole) -> None:
        self._admins[email.lower()] = role

    async def delete(self, email: str) -> None:
        self._admins.pop(email.lower(), None)

    async def is_empty(self) -> bool:
        return not self._admins


@dataclass
class AdminOrg:
    store: AdminOrgStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryAdminOrgStore()

    async def bootstrap_super_admin(self, email: str) -> None:
        await self.store.set(email, AdminRole.super_admin)

    async def invite(self, actor: str, email: str, role: AdminRole) -> str:
        if await self.store.get(actor) is not AdminRole.super_admin:
            raise AdminAuthzError("only a super_admin can invite admins")
        return jwt.encode({"email": email.lower(), "role": role.value, "exp": int(time.time()) + 604800},
                          get_settings().session_secret, algorithm=_ALGO)

    async def accept(self, token: str) -> AdminRole:
        try:
            data = jwt.decode(token, get_settings().session_secret, algorithms=[_ALGO])
        except jwt.PyJWTError as e:
            raise AdminAuthzError("invalid or expired invite") from e
        role = AdminRole(data["role"])
        await self.store.set(data["email"], role)
        return role

    async def remove(self, actor: str, email: str) -> None:
        if await self.store.get(actor) is not AdminRole.super_admin:
            raise AdminAuthzError("only a super_admin can remove admins")
        await self.store.delete(email)

    async def role_of(self, email: str) -> AdminRole | None:
        return await self.store.get(email)

    async def is_empty(self) -> bool:
        return await self.store.is_empty()
