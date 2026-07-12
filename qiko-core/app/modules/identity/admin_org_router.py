"""Admin-organisation RBAC API (super_admin/viewer) - distinct from the product tenant RBAC."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import current_claims, get_admin_org, require_platform_admin
from app.modules.identity.admin_rbac import AdminAuthzError, AdminRole

router = APIRouter(prefix="/admin/org", tags=["admin"])


def _actor_email(claims: dict) -> str:
    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="token has no email")
    return email


@router.post("/bootstrap")
async def bootstrap(claims: dict = Depends(current_claims), org=Depends(get_admin_org)) -> dict:
    """First-run only: the very first authenticated caller becomes super_admin. Once any admin
    exists, this is a no-op (use /invite, super_admin-only, to add more) -- so this can never be
    used to self-escalate after initial setup, and it's keyed by email like everything else here
    (never the tenant role, which every signed-up user satisfies as "owner" of their own tenant)."""
    if not await org.is_empty():
        raise HTTPException(status_code=409, detail="already bootstrapped")
    email = _actor_email(claims)
    await org.bootstrap_super_admin(email)
    return {"super_admin": email}


class InviteBody(BaseModel):
    email: str = Field(min_length=3)
    role: AdminRole = AdminRole.viewer


@router.post("/invite")
async def invite(body: InviteBody, claims: dict = Depends(current_claims), org=Depends(get_admin_org)) -> dict:
    try:
        return {"token": await org.invite(_actor_email(claims), body.email, body.role)}
    except AdminAuthzError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


class AcceptBody(BaseModel):
    token: str = Field(min_length=1)


@router.post("/accept")
async def accept(body: AcceptBody, org=Depends(get_admin_org)) -> dict:
    try:
        return {"role": (await org.accept(body.token)).value}
    except AdminAuthzError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{email}")
async def remove(email: str, claims: dict = Depends(current_claims), org=Depends(get_admin_org)) -> dict:
    try:
        await org.remove(_actor_email(claims), email)
    except AdminAuthzError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return {"removed": email}


@router.get("/role/{email}")
async def role_of(email: str, _role=Depends(require_platform_admin()), org=Depends(get_admin_org)) -> dict:
    """Whether an arbitrary email is a platform admin (and which role) is only the platform
    admin org's own business -- any authenticated tenant customer being able to query it would
    leak who has platform-wide access (OWASP API3 excessive data exposure)."""
    role = await org.role_of(email)
    return {"email": email, "role": role.value if role else None}
