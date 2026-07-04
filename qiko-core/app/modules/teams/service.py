"""Teams & membership with a per-role permission matrix. Reuses the identity Role enum
(owner/admin/editor/viewer). The owner is protected: cannot be demoted or removed."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

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


@dataclass
class TeamService:
    _teams: dict[str, Team] = field(default_factory=dict)

    def create_team(self, tenant: str, owner_id: str) -> Team:
        team = Team(id=uuid.uuid4().hex[:12], tenant=tenant, members={owner_id: Role.owner})
        self._teams[team.id] = team
        return team

    def _owner(self, team: Team) -> str:
        return next(uid for uid, r in team.members.items() if r is Role.owner)

    def add_member(self, team_id: str, user_id: str, role: Role) -> Team:
        if role is Role.owner:
            raise TeamError("a team has exactly one owner")
        self._teams[team_id].members[user_id] = role
        return self._teams[team_id]

    def update_role(self, team_id: str, user_id: str, role: Role) -> Team:
        team = self._teams[team_id]
        if user_id == self._owner(team):
            raise TeamError("cannot change the owner's role")
        if role is Role.owner:
            raise TeamError("a team has exactly one owner")
        team.members[user_id] = role
        return team

    def remove_member(self, team_id: str, user_id: str) -> Team:
        team = self._teams[team_id]
        if user_id == self._owner(team):
            raise TeamError("cannot remove the owner")
        team.members.pop(user_id, None)
        return team

    def members(self, team_id: str) -> dict[str, Role]:
        return dict(self._teams[team_id].members)
