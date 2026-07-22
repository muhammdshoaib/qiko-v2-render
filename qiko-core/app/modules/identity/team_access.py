"""Team Access support: role label mapping + a tenant-scoped pending-invite registry.

The Creator Settings > Team tab surfaces the tenant's identity users as the member list
(so real tenant users show up immediately) and separates them into two views:

- Accepted: users that exist in the identity store (they can log in).
- Pending: email and role offers created by Settings > Team. The invitation email carries a signed,
  expiring token; signup consumes the exact pending record and applies its tenant and role.

Role label mapping (backend Role enum <-> stage "Team Access" labels):
    viewer -> "User"
    editor -> "Creator"
    admin  -> "Admin"
    owner  -> "Owner"  (protected account owner; not offered as an assignable role)

Only viewer/editor/admin are assignable through Team Access; owner is protected end to end
(cannot be re-assigned, invited, or removed), so the last owner of a tenant is never lost.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.modules.identity.rbac import Role

# Backend Role -> stage display label.
ROLE_LABELS: dict[Role, str] = {
    Role.viewer: "User",
    Role.editor: "Creator",
    Role.admin: "Admin",
    Role.owner: "Owner",
}

# The roles an owner/admin may assign to a member through Team Access (owner excluded).
ASSIGNABLE_ROLES: tuple[Role, ...] = (Role.viewer, Role.editor, Role.admin)


@dataclass
class PendingInvite:
    email: str
    role: Role
    invited_at: float


@dataclass
class PendingInviteStore:
    """In-memory pending invites, keyed by tenant, for dev/tests. Fully tenant-scoped: a tenant
    can only ever read/write its own invites. Cleared on process restart. The Postgres-backed
    SqlPendingInviteStore (swapped in under USE_DB_STORES) is the durable, cross-process
    implementation with the same async interface."""

    _by_tenant: dict[str, dict[str, PendingInvite]] = field(default_factory=dict)

    async def list(self, tenant: str) -> list[PendingInvite]:
        return sorted(self._by_tenant.get(tenant, {}).values(), key=lambda i: i.invited_at)

    async def get(self, tenant: str, email: str) -> PendingInvite | None:
        return self._by_tenant.get(tenant, {}).get(email.lower())

    async def add(self, tenant: str, email: str, role: Role) -> PendingInvite:
        invite = PendingInvite(email=email.lower(), role=role, invited_at=time.time())
        self._by_tenant.setdefault(tenant, {})[invite.email] = invite
        return invite

    async def remove(self, tenant: str, email: str) -> bool:
        return self._by_tenant.get(tenant, {}).pop(email.lower(), None) is not None
