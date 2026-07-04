"""Admin-organisation RBAC API (super_admin/viewer) - distinct from the product tenant RBAC."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import current_claims, get_admin_org, require_role
from app.modules.identity.admin_rbac import AdminAuthzError, AdminRole
from app.modules.identity.rbac import Role

router = APIRouter(prefix="/admin/org", tags=["admin"])


@router.post("/bootstrap")
def bootstrap(claims: dict = Depends(current_claims), _r: dict = Depends(require_role(Role.owner)),
              org=Depends(get_admin_org)) -> dict:
    org.bootstrap_super_admin(claims["sub"])
    return {"super_admin": claims["sub"]}


class InviteBody(BaseModel):
    email: str = Field(min_length=3)
    role: AdminRole = AdminRole.viewer


@router.post("/invite")
def invite(body: InviteBody, claims: dict = Depends(current_claims), org=Depends(get_admin_org)) -> dict:
    try:
        return {"token": org.invite(claims["sub"], body.email, body.role)}
    except AdminAuthzError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


class AcceptBody(BaseModel):
    token: str = Field(min_length=1)


@router.post("/accept")
def accept(body: AcceptBody, org=Depends(get_admin_org)) -> dict:
    try:
        return {"role": org.accept(body.token).value}
    except AdminAuthzError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{email}")
def remove(email: str, claims: dict = Depends(current_claims), org=Depends(get_admin_org)) -> dict:
    try:
        org.remove(claims["sub"], email)
    except AdminAuthzError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return {"removed": email}


@router.get("/role/{email}")
def role_of(email: str, _claims: dict = Depends(current_claims), org=Depends(get_admin_org)) -> dict:
    role = org.role_of(email)
    return {"email": email, "role": role.value if role else None}
