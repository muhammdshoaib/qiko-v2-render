"""Teams HTTP API (tenant-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import authed_tenant, current_claims, get_teams, require_role
from app.modules.identity.rbac import Role
from app.modules.teams.invites import InviteError, accept_invite, create_invite, set_invite_password
from app.modules.audit import registry as audit_actions
from app.modules.audit import service as audit
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
async def create_team(body: CreateTeamBody, _tenant: str = Depends(authed_tenant),
                      _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    return _members(await svc.create_team(_tenant, body.owner_id))


@router.get("/{team_id}/members")
async def members(team_id: str, tenant: str = Depends(authed_tenant), svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
    return {"team_id": team_id, "members": {u: r.value for u, r in (await svc.members(team_id)).items()}}


async def _record_access(request, action: str, tenant: str, claims: dict, team_id: str,
                         user_id: str, after: dict, before: dict | None = None) -> None:
    """One shape for all three membership mutations.

    Team membership is a second, independent way to reach a tenant's data, alongside the identity
    role. An access review that only looked at identity roles would miss every grant made here, which
    is the failure mode that makes a leaver sample wrong rather than merely incomplete.
    """
    await audit.record(request.app.state.audit, audit.AuditEvent(
        action=action, target_id=user_id, tenant_id=tenant, actor_type=audit.USER,
        actor_id=str(claims.get("sub") or ""), actor_label=str(claims.get("email") or ""),
        changes=audit.diff(action, before or {}, after),
        metadata={"team_id": team_id, "via": "team"}), request=request)


@router.post("/{team_id}/members")
async def add_member(team_id: str, body: MemberBody, request: Request,
                     claims: dict = Depends(current_claims), tenant: str = Depends(authed_tenant),
                     _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
    try:
        members = _members(await svc.add_member(team_id, body.user_id, body.role))
        await _record_access(request, audit_actions.TENANT_MEMBER_ADDED, tenant, claims,
                             team_id, body.user_id, {"role": body.role.value})
        return members
    except TeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail="team not found") from e


class RoleBody(BaseModel):
    role: Role


@router.put("/{team_id}/members/{user_id}")
async def update_member(team_id: str, user_id: str, body: RoleBody, request: Request,
                        claims: dict = Depends(current_claims), tenant: str = Depends(authed_tenant),
                        _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
    try:
        # Captured first: an access review cannot tell what a member was demoted FROM otherwise, and
        # the identity-side equivalent has always recorded it.
        existing = (await svc.members(team_id)).get(user_id)
        members = _members(await svc.update_role(team_id, user_id, body.role))
        await _record_access(request, audit_actions.TENANT_ROLE_CHANGED, tenant, claims,
                             team_id, user_id, {"role": body.role.value},
                             before={"role": existing.value if existing else None})
        return members
    except TeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail="team not found") from e


@router.delete("/{team_id}/members/{user_id}")
async def remove_member(team_id: str, user_id: str, request: Request,
                        claims: dict = Depends(current_claims), tenant: str = Depends(authed_tenant),
                        _r: dict = _admin, svc=Depends(get_teams)) -> dict:
    await _get_owned_team(team_id, tenant, svc)
    try:
        members = _members(await svc.remove_member(team_id, user_id))
        await _record_access(request, audit_actions.TENANT_MEMBER_REMOVED, tenant, claims,
                             team_id, user_id, {})
        return members
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
