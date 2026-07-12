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


async def _get_owned_team(team_id: str, tenant: str, svc):
    """Every team_id-scoped endpoint below must go through this: TeamService methods take a bare
    team_id with no tenant check of their own, so without this gate any authenticated user from
    any tenant could read/modify another tenant's team (cross-tenant BOLA -- OWASP API1). 404
    (not 403) so an outsider can't even tell the team_id exists in a different tenant."""
    team = await svc.get(team_id)
    if team is None or team.tenant != tenant:
        raise HTTPException(status_code=404, detail="team not found")
    return team


@router.post("")
async def create_team(body: CreateTeamBody, _tenant: str = Depends(authed_tenant), svc=Depends(get_teams)) -> dict:
    return _members(await svc.create_team(_tenant, body.owner_id))


@router.get("/{team_id}/members")
async def members(team_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
    return {"team_id": team_id, "members": {u: r.value for u, r in (await svc.members(team_id)).items()}}


@router.post("/{team_id}/members")
async def add_member(team_id: str, body: MemberBody, tenant: str = Depends(authed_tenant), svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
    try:
        return _members(await svc.add_member(team_id, body.user_id, body.role))
    except TeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail="team not found") from e


class RoleBody(BaseModel):
    role: Role


@router.put("/{team_id}/members/{user_id}")
async def update_member(team_id: str, user_id: str, body: RoleBody, tenant: str = Depends(authed_tenant),
                        _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
    try:
        return _members(await svc.update_role(team_id, user_id, body.role))
    except TeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail="team not found") from e


@router.delete("/{team_id}/members/{user_id}")
async def remove_member(team_id: str, user_id: str, tenant: str = Depends(authed_tenant),
                        _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
    try:
        return _members(await svc.remove_member(team_id, user_id))
    except TeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail="team not found") from e


class InviteBody(BaseModel):
    email: str = Field(min_length=3)
    role: Role = Role.editor


@router.post("/{team_id}/invites")
async def invite(team_id: str, body: InviteBody, tenant: str = Depends(authed_tenant),
                 _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
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
async def set_password(body: SetPasswordBody, svc=Depends(get_teams)) -> dict:
    try:
        rec = await set_invite_password(svc, body.token, body.password)
    except InviteError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"email": rec["email"], "team_id": rec["team_id"]}
