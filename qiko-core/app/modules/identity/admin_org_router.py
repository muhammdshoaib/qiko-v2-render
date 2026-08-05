"""Admin-organisation RBAC API (super_admin/viewer) - distinct from the product tenant RBAC."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.deps import (
    current_claims,
    get_admin_org,
    require_platform_admin,
    require_platform_capability,
    require_platform_super_admin,
)
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import (
    AdminAuthzError,
    AdminIdentity,
    AdminRole,
    Capability,
    parse_capabilities,
)

# Documents BOTH halves of the double-submit pair, like admin/router.py, so the generated client and
# anyone reading the schema knows the mutation needs the header AND the matching cookie.
_CSRF_OPENAPI = {
    "parameters": [
        {"in": "header", "name": csrf.CSRF_HEADER, "required": True,
         "schema": {"type": "string"},
         "description": "Double-submit CSRF token; must equal the qiko_csrf cookie."},
        {"in": "cookie", "name": csrf.CSRF_COOKIE, "required": True,
         "schema": {"type": "string"},
         "description": "Double-submit CSRF cookie; must equal the x-csrf-token header."},
    ]
}


def _identity_json(identity: AdminIdentity) -> dict:
    return {"email": identity.email, "role": identity.role.value,
            "capabilities": sorted(c.value for c in identity.capabilities)}

router = APIRouter(prefix="/admin/org", tags=["admin"])


def _validated_email(email: str) -> str:
    """A platform-admin key must look like an address.

    Without this, PUT /admin/org/audit created a platform_admins row literally keyed "audit", and a
    value longer than the 320-char column raised a database error as an unhandled 500.
    """
    candidate = email.strip().lower()
    if len(candidate) > 320 or "@" not in candidate.strip("@") or any(c.isspace() for c in candidate):
        raise HTTPException(status_code=422, detail="email must be a single valid address")
    return candidate


def _actor_email(claims: dict) -> str:
    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="token has no email")
    return email


@router.post("/bootstrap")
async def bootstrap(claims: dict = Depends(current_claims), org=Depends(get_admin_org)) -> dict:
    """Development-only bootstrap. Non-dev platform admins are provisioned by an operator, never by
    the first public tenant user to reach an endpoint."""
    if not get_settings().debug:
        raise HTTPException(status_code=404, detail="not found")
    if not await org.is_empty():
        raise HTTPException(status_code=409, detail="already bootstrapped")
    email = _actor_email(claims)
    await org.bootstrap_super_admin(email)
    return {"super_admin": email}


class InviteBody(BaseModel):
    email: str = Field(min_length=3)
    role: AdminRole = AdminRole.viewer


@router.post("/invite", openapi_extra=_CSRF_OPENAPI)
async def invite(body: InviteBody, request: Request, claims: dict = Depends(current_claims),
                 _role=Depends(require_platform_super_admin()), org=Depends(get_admin_org)) -> dict:
    """Mint an invite token. DEV-ONLY on purpose.

    The token is stateless: no jti, no server-side record, valid for 7 days, and its value is
    returned in this response body for the caller to paste into email or chat. That makes it a
    replayable, unrevocable bearer credential for the highest privilege in the system - a revoked
    admin could re-post the same token and reinstate themselves, and because accept() writes through
    store.set() rather than the audited grant path, the reinstatement would leave no audit row.
    Production granting goes through the audited, capability-gated PUT /admin/org/{email}, and
    first-admin provisioning through scripts/provision_platform_admin.py. Rebuilding this on the
    PendingTeamInvite pattern (single-use row consumed under FOR UPDATE, emailed to the invitee) is
    the prerequisite for enabling it outside dev.
    """
    if not get_settings().debug:
        raise HTTPException(status_code=404, detail="not found")
    csrf.require_csrf(request)
    try:
        return {"token": await org.invite(_actor_email(claims), body.email, body.role)}
    except AdminAuthzError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


class AcceptBody(BaseModel):
    token: str = Field(min_length=1)


@router.post("/accept")
async def accept(body: AcceptBody, claims: dict = Depends(current_claims),
                 org=Depends(get_admin_org)) -> dict:
    """Redeem a platform-admin invite. DEV-ONLY, see invite() for why.

    The identity checks below are kept even in dev: the endpoint used to have no authentication at
    all, so anyone holding a leaked invite could mint platform-admin access for the invited email.
    """
    if not get_settings().debug:
        raise HTTPException(status_code=404, detail="not found")
    if not claims.get("mfa"):
        raise HTTPException(status_code=403, detail="two-factor authentication required")
    caller = (claims.get("email") or "").lower()
    if not caller:
        raise HTTPException(status_code=403, detail="token has no email")
    invited = _invited_email(body.token)
    if invited != caller:
        # Same generic message as a bad token: never reveal who an invite was addressed to.
        raise HTTPException(status_code=400, detail="invalid or expired invite")
    try:
        return {"role": (await org.accept(body.token)).value}
    except AdminAuthzError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{email}", openapi_extra=_CSRF_OPENAPI)
async def remove(email: str, request: Request,
                 reason: str | None = Query(default=None, max_length=1000),
                 claims: dict = Depends(current_claims),
                 _identity=Depends(require_platform_capability(Capability.manage_admins)),
                 org=Depends(get_admin_org)) -> dict:
    csrf.require_csrf(request)
    email = _validated_email(email)
    if await org.role_of(email) is AdminRole.super_admin:
        raise HTTPException(status_code=409, detail="super-admin removal requires operator recovery process")
    try:
        # Goes through AdminOrg.revoke so the removal is audited; the previous path wrote no trail.
        await org.revoke(_actor_email(claims), email, reason=reason)
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


def _invited_email(token: str) -> str | None:
    """The email an invite was addressed to, or None if the token is unusable."""
    import jwt

    try:
        data = jwt.decode(token, get_settings().session_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if data.get("type") != "platform_admin_invite":
        return None
    email = data.get("email")
    return str(email).lower() if email else None


@router.get("")
async def list_admins(_identity=Depends(require_platform_capability(Capability.manage_admins)),
                      org=Depends(get_admin_org)) -> dict:
    """The platform-admin directory. There was no way to enumerate platform admins at all, so the
    admin UI could only look one up by exact email - you could not answer "who has access?"."""
    return {"admins": [_identity_json(identity) for identity in await org.list_admins()]}


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AdminRole
    # None means "use the role default"; a list means exactly these capabilities.
    capabilities: list[str] | None = None
    reason: str | None = Field(default=None, max_length=1000)


@router.put("/{email}", openapi_extra=_CSRF_OPENAPI)
async def grant(email: str, body: GrantBody, request: Request,
                claims: dict = Depends(current_claims),
                _identity=Depends(require_platform_capability(Capability.manage_admins)),
                org=Depends(get_admin_org)) -> dict:
    csrf.require_csrf(request)
    email = _validated_email(email)
    try:
        capabilities = parse_capabilities(body.capabilities)
    except ValueError as e:
        # Reject an unknown capability name instead of silently dropping it, which would quietly
        # grant less than the operator believed they granted.
        raise HTTPException(status_code=422, detail="unknown capability") from e
    try:
        identity = await org.grant(_actor_email(claims), email, body.role, capabilities,
                                   reason=body.reason)
    except AdminAuthzError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return _identity_json(identity)


@router.get("/audit")
async def audit(limit: int = Query(default=50, ge=1, le=200),
                _identity=Depends(require_platform_capability(Capability.manage_admins)),
                org=Depends(get_admin_org)) -> dict:
    """Every grant and revoke, newest first. Platform admin is the highest privilege in the system
    and previously left no trail whatsoever."""
    return {"entries": [{
        "id": entry.id, "email": entry.email, "changed_by_email": entry.changed_by_email,
        "previous_role": entry.previous_role, "role": entry.role,
        "previous_capabilities": entry.previous_capabilities, "capabilities": entry.capabilities,
        "reason": entry.reason, "created_at": entry.created_at.isoformat(),
    } for entry in await org.list_audit(limit=limit)]}
