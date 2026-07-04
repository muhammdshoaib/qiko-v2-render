"""Teams HTTP API (tenant-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, get_teams, require_role
from app.modules.identity.rbac import Role
from app.modules.teams.invites import InviteError, accept_invite, create_invite, set_invite_password
from app.modules.teams.service import TeamError

router = APIRouter(prefix="/teams", tags=["teams"])
_admin = Depends(require_role(Role.admin))


class CreateTeamBody(BaseModel):
    owner_id: str = Field(min_length=1)


class MemberBody(BaseModel):
    user_id: str = Field(min_length=1)
    role: Role


def _members(team) -> dict:
    return {"team_id": team.id, "members": {uid: r.value for uid, r in team.members.items()}}


@router.post("")
def create_team(body: CreateTeamBody, _tenant: str = Depends(authed_tenant), svc=Depends(get_teams)) -> dict:
    return _members(svc.create_team(_tenant, body.owner_id))


@router.get("/{team_id}/members")
def members(team_id: str, _tenant: str = Depends(authed_tenant), svc=Depends(get_teams)) -> dict:
    try:
        return {"team_id": team_id, "members": {u: r.value for u, r in svc.members(team_id).items()}}
    except KeyError as e:
        raise HTTPException(status_code=404, detail="team not found") from e


@router.post("/{team_id}/members")
def add_member(team_id: str, body: MemberBody, _tenant: str = Depends(authed_tenant), svc=Depends(get_teams)) -> dict:
    try:
        return _members(svc.add_member(team_id, body.user_id, body.role))
    except TeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail="team not found") from e


class RoleBody(BaseModel):
    role: Role


@router.put("/{team_id}/members/{user_id}")
def update_member(team_id: str, user_id: str, body: RoleBody, _tenant: str = Depends(authed_tenant),
                  _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    try:
        return _members(svc.update_role(team_id, user_id, body.role))
    except TeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{team_id}/members/{user_id}")
def remove_member(team_id: str, user_id: str, _tenant: str = Depends(authed_tenant),
                  _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    try:
        return _members(svc.remove_member(team_id, user_id))
    except TeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class InviteBody(BaseModel):
    email: str = Field(min_length=3)
    role: Role = Role.editor


@router.post("/{team_id}/invites")
def invite(team_id: str, body: InviteBody, _tenant: str = Depends(authed_tenant), _r: dict = _admin) -> dict:
    return {"token": create_invite(team_id, body.email, body.role)}


class AcceptBody(BaseModel):
    token: str = Field(min_length=1)


@router.post("/invites/accept")
def accept(body: AcceptBody) -> dict:
    try:
        return accept_invite(body.token)
    except InviteError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class SetPasswordBody(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8)


@router.post("/invites/set-password")
def set_password(body: SetPasswordBody, svc=Depends(get_teams)) -> dict:
    try:
        rec = set_invite_password(svc, body.token, body.password)
    except InviteError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"email": rec["email"], "team_id": rec["team_id"]}
