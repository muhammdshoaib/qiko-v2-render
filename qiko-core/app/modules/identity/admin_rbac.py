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
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

import jwt

from app.core.config import get_settings

_ALGO = "HS256"


class AdminRole(str, Enum):
    super_admin = "super_admin"
    viewer = "viewer"


class Capability(str, Enum):
    """Fine-grained platform-admin permissions.

    The two roles stay as the coarse grouping (and remain the only thing the DB `role` column holds),
    but several admin surfaces are specified as "permission-restricted" -- AI spend, system stats,
    cost caps -- and "super_admin or nothing" is too blunt for those: someone who needs to read the
    cost dashboard should not thereby be able to disable a customer's workers.

    A role implies a DEFAULT set (below). An explicit per-admin set overrides it, so a viewer can be
    granted exactly one extra capability without becoming a super_admin.
    """

    # Deliberately ONLY the capabilities that gate a real endpoint today. Shipping names that
    # nothing enforces would be worse than not having them: an operator would believe they had
    # applied least privilege when they had only filtered a menu. view_ai_cost, set_cost_caps and
    # view_system_stats arrive with the endpoints they gate (QIK-517/518/522).
    view_customers = "view_customers"
    manage_customers = "manage_customers"
    manage_workers = "manage_workers"
    manage_billing = "manage_billing"
    manage_admins = "manage_admins"


# A super_admin keeps everything, so today's behaviour is unchanged. A viewer keeps read-only
# access, which is what the existing gates already gave it.
_DEFAULTS: dict[AdminRole, frozenset[Capability]] = {
    AdminRole.super_admin: frozenset(Capability),
    AdminRole.viewer: frozenset({Capability.view_customers}),
}


def default_capabilities(role: AdminRole) -> frozenset[Capability]:
    return _DEFAULTS[role]


def parse_capabilities(values: Iterable[str] | None) -> frozenset[Capability] | None:
    """None means "no explicit grant, fall back to the role default". Unknown names are rejected
    rather than silently dropped, so a typo in a grant can never quietly widen or narrow access."""
    if values is None:
        return None
    return frozenset(Capability(value) for value in values)


def effective_capabilities(role: AdminRole,
                           explicit: Iterable[Capability] | None = None) -> frozenset[Capability]:
    if explicit is None:
        return default_capabilities(role)
    granted = frozenset(explicit)
    # A super_admin cannot be narrowed below admin management: that would make the platform
    # unrecoverable if the last super_admin locked themselves out of it.
    if role is AdminRole.super_admin:
        return granted | {Capability.manage_admins}
    return granted


@dataclass(frozen=True)
class AdminIdentity:
    """A platform admin plus the capabilities that actually apply to them."""

    email: str
    role: AdminRole
    capabilities: frozenset[Capability]

    def can(self, capability: Capability) -> bool:
        return capability in self.capabilities


def can_invite_admins(role: AdminRole) -> bool:
    return role is AdminRole.super_admin


class AdminAuthzError(Exception):
    pass


@dataclass(frozen=True)
class AdminGrantAudit:
    """One recorded change to a platform admin's role or capabilities."""

    id: int | None
    email: str
    changed_by_email: str
    previous_role: str | None
    role: str | None
    previous_capabilities: list[str] | None
    capabilities: list[str] | None
    reason: str | None
    created_at: datetime


class AdminOrgStore(Protocol):
    async def get(self, email: str) -> AdminRole | None: ...
    async def set(self, email: str, role: AdminRole) -> None: ...
    async def delete(self, email: str) -> None: ...
    async def is_empty(self) -> bool: ...
    async def get_identity(self, email: str) -> AdminIdentity | None: ...
    async def list_admins(self) -> list[AdminIdentity]: ...
    async def grant(self, email: str, role: AdminRole,
                    capabilities: frozenset[Capability] | None, *,
                    changed_by_email: str, reason: str | None) -> AdminIdentity: ...
    async def revoke(self, email: str, *, changed_by_email: str,
                     reason: str | None) -> None: ...
    async def list_audit(self, *, limit: int = 50) -> list[AdminGrantAudit]: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class InMemoryAdminOrgStore:
    _admins: dict[str, AdminRole] = field(default_factory=dict)
    _capabilities: dict[str, frozenset[Capability]] = field(default_factory=dict)
    _audit: list[AdminGrantAudit] = field(default_factory=list)

    async def get(self, email: str) -> AdminRole | None:
        return self._admins.get(email.lower())

    async def set(self, email: str, role: AdminRole) -> None:
        self._admins[email.lower()] = role

    async def delete(self, email: str) -> None:
        key = email.lower()
        self._admins.pop(key, None)
        self._capabilities.pop(key, None)

    async def is_empty(self) -> bool:
        return not self._admins

    async def get_identity(self, email: str) -> AdminIdentity | None:
        key = email.lower()
        role = self._admins.get(key)
        if role is None:
            return None
        return AdminIdentity(email=key, role=role,
                             capabilities=effective_capabilities(role, self._capabilities.get(key)))

    async def list_admins(self) -> list[AdminIdentity]:
        return [await self.get_identity(email) for email in sorted(self._admins)]  # type: ignore[misc]

    async def grant(self, email: str, role: AdminRole,
                    capabilities: frozenset[Capability] | None, *,
                    changed_by_email: str, reason: str | None) -> AdminIdentity:
        key = email.lower()
        previous_role = self._admins.get(key)
        previous_caps = self._capabilities.get(key)
        stored = frozenset(effective_capabilities(role, capabilities)) if capabilities is not None else None
        self._admins[key] = role
        if stored is None:
            self._capabilities.pop(key, None)
        else:
            self._capabilities[key] = stored
        identity = await self.get_identity(key)
        # Same no-op suppression as the SQL store: without it the "a no-op grant writes no audit
        # row" property would hold only in production, and every API test runs against this store.
        if not (previous_role is role and previous_caps == stored):
            self._record(key, changed_by_email, previous_role, role, previous_caps, stored, reason)
        return identity  # type: ignore[return-value]

    async def revoke(self, email: str, *, changed_by_email: str, reason: str | None) -> None:
        key = email.lower()
        previous_role = self._admins.get(key)
        previous_caps = self._capabilities.get(key)
        await self.delete(key)
        if previous_role is not None:
            self._record(key, changed_by_email, previous_role, None, previous_caps, None, reason)

    async def list_audit(self, *, limit: int = 50) -> list[AdminGrantAudit]:
        return list(reversed(self._audit))[:max(1, min(limit, 200))]

    def _record(self, email: str, actor: str, previous_role: AdminRole | None,
                role: AdminRole | None, previous_caps: frozenset[Capability] | None,
                caps: frozenset[Capability] | None, reason: str | None) -> None:
        self._audit.append(AdminGrantAudit(
            id=len(self._audit) + 1, email=email, changed_by_email=actor,
            previous_role=previous_role.value if previous_role else None,
            role=role.value if role else None,
            previous_capabilities=sorted(c.value for c in previous_caps) if previous_caps is not None else None,
            capabilities=sorted(c.value for c in caps) if caps is not None else None,
            reason=(reason or "").strip() or None, created_at=_now()))


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
        return jwt.encode({"type": "platform_admin_invite", "email": email.lower(),
                           "role": role.value, "exp": int(time.time()) + 604800},
                          get_settings().session_secret, algorithm=_ALGO)

    async def accept(self, token: str) -> AdminRole:
        try:
            data = jwt.decode(token, get_settings().session_secret, algorithms=[_ALGO])
            if data.get("type") != "platform_admin_invite":
                raise AdminAuthzError("invalid or expired invite")
            email = str(data["email"]).lower()
            role = AdminRole(data["role"])
        except (KeyError, TypeError, ValueError, jwt.PyJWTError) as e:
            raise AdminAuthzError("invalid or expired invite") from e
        await self.store.set(email, role)
        return role

    async def remove(self, actor: str, email: str) -> None:
        if await self.store.get(actor) is not AdminRole.super_admin:
            raise AdminAuthzError("only a super_admin can remove admins")
        await self.store.delete(email)

    async def role_of(self, email: str) -> AdminRole | None:
        return await self.store.get(email)

    async def identity_of(self, email: str) -> AdminIdentity | None:
        return await self.store.get_identity(email)

    async def list_admins(self) -> list[AdminIdentity]:
        return await self.store.list_admins()

    async def grant(self, actor: str, email: str, role: AdminRole,
                    capabilities: frozenset[Capability] | None, *,
                    reason: str | None = None) -> AdminIdentity:
        """Assign a role and (optionally) an explicit capability set.

        manage_admins is deliberately NOT a root primitive that can be delegated to a viewer:
        without the guards below, one checkbox would let a viewer mint a super_admin they control
        (which then passes every role-gated mutation), demote every peer super_admin in bypass of
        the 409 invariant the removal path enforces, and widen their own capability set while the
        role column still read "viewer".
        """
        actor_identity = await self.store.get_identity(actor)
        if actor_identity is None or not actor_identity.can(Capability.manage_admins):
            raise AdminAuthzError("only an admin with manage_admins can assign roles")
        # No self-service at all, not just no self-role-change: self-widening kept the role column
        # unchanged, so a role-based review would have shown nothing.
        if actor.lower() == email.lower():
            raise AdminAuthzError("an admin cannot change their own access")
        actor_is_super = actor_identity.role is AdminRole.super_admin
        target = await self.store.get_identity(email)
        if role is AdminRole.super_admin and not actor_is_super:
            raise AdminAuthzError("only a super_admin can appoint a super_admin")
        if target is not None and target.role is AdminRole.super_admin and not actor_is_super:
            # Mirrors the removal path's refusal to touch a super_admin: otherwise the invariant is
            # bypassable by demotion instead of deletion.
            raise AdminAuthzError("only a super_admin can change a super_admin")
        if capabilities is not None and Capability.manage_admins in capabilities and not actor_is_super:
            raise AdminAuthzError("only a super_admin can delegate manage_admins")
        return await self.store.grant(email, role, capabilities,
                                      changed_by_email=actor, reason=reason)

    async def revoke(self, actor: str, email: str, *, reason: str | None = None) -> None:
        actor_identity = await self.store.get_identity(actor)
        if actor_identity is None or not actor_identity.can(Capability.manage_admins):
            raise AdminAuthzError("only an admin with manage_admins can remove admins")
        if actor.lower() == email.lower():
            raise AdminAuthzError("an admin cannot remove themselves")
        target = await self.store.get_identity(email)
        if target is not None and target.role is AdminRole.super_admin \
                and actor_identity.role is not AdminRole.super_admin:
            raise AdminAuthzError("only a super_admin can remove a super_admin")
        await self.store.revoke(email, changed_by_email=actor, reason=reason)

    async def list_audit(self, *, limit: int = 50) -> list[AdminGrantAudit]:
        return await self.store.list_audit(limit=limit)

    async def is_empty(self) -> bool:
        return await self.store.is_empty()
