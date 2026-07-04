import pytest

from app.modules.identity.rbac import Role
from app.modules.identity.security import verify_password
from app.modules.teams.invites import (
    InviteError,
    accept_invite,
    create_invite,
    set_invite_password,
)
from app.modules.teams.service import TeamService


def test_invite_roundtrip():
    token = create_invite("team-1", "New@X.com", Role.editor)
    data = accept_invite(token)
    assert data["team_id"] == "team-1" and data["email"] == "new@x.com" and data["role"] == "editor"


def test_expired_and_tampered_rejected():
    with pytest.raises(InviteError):
        accept_invite(create_invite("t", "e@x.com", Role.viewer, ttl=-1))  # already expired
    with pytest.raises(InviteError):
        accept_invite("not.a.valid.token")


def test_set_password_adds_member_and_hashes():
    teams = TeamService()
    team = teams.create_team("acme", "owner")
    token = create_invite(team.id, "member@x.com", Role.editor)
    rec = set_invite_password(teams, token, "s3cret-pw")
    assert teams.members(team.id)["member@x.com"] is Role.editor
    assert rec["password_hash"] != "s3cret-pw" and verify_password("s3cret-pw", rec["password_hash"])
