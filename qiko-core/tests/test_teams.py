import pytest

from app.modules.identity.rbac import Role
from app.modules.teams.service import PERMISSIONS, TeamError, TeamService, can


def test_permission_matrix():
    assert can(Role.owner, "view_billing") and can(Role.owner, "edit_workers")
    assert can(Role.editor, "edit_workers") and not can(Role.editor, "view_billing")
    assert PERMISSIONS[Role.viewer] == set()


async def test_create_team_makes_owner():
    svc = TeamService()
    team = await svc.create_team("acme", "u-owner")
    assert team.members == {"u-owner": Role.owner}


async def test_add_update_remove_member_with_owner_protection():
    svc = TeamService()
    team = await svc.create_team("acme", "owner")
    await svc.add_member(team.id, "u2", Role.editor)
    assert (await svc.members(team.id))["u2"] is Role.editor
    await svc.update_role(team.id, "u2", Role.admin)
    assert (await svc.members(team.id))["u2"] is Role.admin
    await svc.remove_member(team.id, "u2")
    assert "u2" not in await svc.members(team.id)

    # owner is protected
    with pytest.raises(TeamError):
        await svc.update_role(team.id, "owner", Role.viewer)
    with pytest.raises(TeamError):
        await svc.remove_member(team.id, "owner")
    with pytest.raises(TeamError):
        await svc.add_member(team.id, "u3", Role.owner)  # only one owner
