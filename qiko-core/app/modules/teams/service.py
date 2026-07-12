"""Teams & membership with a per-role permission matrix. Reuses the identity Role enum
(owner/admin/editor/viewer). The owner is protected: cannot be demoted or removed."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.modules.identity.rbac import Role

# Per-role capabilities (function-level authz for team actions).
PERMISSIONS: dict[Role, set[str]] = {
    Role.owner: {"manage_team", "edit_workers", "view_billing"},
    Role.admin: {"manage_team", "edit_workers", "view_billing"},
    Role.editor: {"edit_workers"},
    Role.viewer: set(),
}


def can(role: Role, capability: str) -> bool:
    return capability in PERMISSIONS.get(role, set())


class TeamError(Exception):
    pass


@dataclass
class Team:
    id: str
    tenant: str
    members: dict[str, Role] = field(default_factory=dict)  # user_id -> role


class TeamStore(Protocol):
    async def add(self, team: Team) -> Team: ...
    async def get(self, team_id: str) -> Team | None: ...
    async def set_member(self, team_id: str, user_id: str, role: Role) -> Team: ...
    async def remove_member(self, team_id: str, user_id: str) -> Team: ...


@dataclass
class InMemoryTeamStore:
    _teams: dict[str, Team] = field(default_factory=dict)

    async def add(self, team: Team) -> Team:
        self._teams[team.id] = team
        return team

    async def get(self, team_id: str) -> Team | None:
        return self._teams.get(team_id)

    async def set_member(self, team_id: str, user_id: str, role: Role) -> Team:
        team = self._teams[team_id]
        team.members[user_id] = role
        return team

    async def remove_member(self, team_id: str, user_id: str) -> Team:
        team = self._teams[team_id]
        team.members.pop(user_id, None)
        return team


@dataclass
class TeamService:
    store: TeamStore = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryTeamStore()

    async def create_team(self, tenant: str, owner_id: str) -> Team:
        team = Team(id=uuid.uuid4().hex[:12], tenant=tenant, members={owner_id: Role.owner})
        return await self.store.add(team)

    async def get(self, team_id: str) -> Team | None:
        """Public lookup (unlike `_get`, doesn't raise) -- callers that need to check tenant
        ownership before doing anything else (see teams/router.py) need this rather than the
        KeyError-raising internal helper."""
        return await self.store.get(team_id)

    async def _get(self, team_id: str) -> Team:
        team = await self.store.get(team_id)
        if team is None:
            raise KeyError(team_id)
        return team

    def _owner(self, team: Team) -> str:
        return next(uid for uid, r in team.members.items() if r is Role.owner)

    async def add_member(self, team_id: str, user_id: str, role: Role) -> Team:
        if role is Role.owner:
            raise TeamError("a team has exactly one owner")
        await self._get(team_id)
        return await self.store.set_member(team_id, user_id, role)

    async def update_role(self, team_id: str, user_id: str, role: Role) -> Team:
        team = await self._get(team_id)
        if user_id == self._owner(team):
            raise TeamError("cannot change the owner's role")
        if role is Role.owner:
            raise TeamError("a team has exactly one owner")
        return await self.store.set_member(team_id, user_id, role)

    async def remove_member(self, team_id: str, user_id: str) -> Team:
        team = await self._get(team_id)
        if user_id == self._owner(team):
            raise TeamError("cannot remove the owner")
        return await self.store.remove_member(team_id, user_id)

    async def members(self, team_id: str) -> dict[str, Role]:
        team = await self._get(team_id)
        return dict(team.members)
