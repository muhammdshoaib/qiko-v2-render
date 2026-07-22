"""Team Access API (tenant-scoped): list the tenant's users, invite new ones, change roles, and
remove them. Backs the Creator Settings > Team tab.

Wiring choice: the member list is the identity UserStore's tenant users (list_by_tenant), so the
tenant's real, login-capable users (Accepted) show up immediately, plus a registry of pending role
offers. Invitation emails carry a short-lived signed token; public signup consumes the matching
server-side pending record and applies its tenant and role. Mutations are RBAC-guarded to owner/admin
(require_role(Role.admin) -- an owner
outranks an admin within their own tenant). Every lookup is tenant-scoped (a user_id belonging to
another tenant returns 404, not 403, so an outsider can't probe ids -- OWASP API1/BOLA).

The account owner is protected: their role can't be changed and they can't be removed, and the
owner role is never assignable through this API, so the last owner of a tenant is never lost.

See app.modules.identity.team_access for the Role <-> label mapping (viewer=User, editor=Creator,
admin=Admin, owner=Owner) and the pending-invite store.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.deps import authed_tenant, get_pending_invites, require_role
from app.modules.email.sender import EmailSender, get_email_sender
from app.modules.email.templates import team_invite_email
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.store import User, UserStore
from app.modules.identity.team_access import (
    ASSIGNABLE_ROLES,
    ROLE_LABELS,
    PendingInviteStore,
)
from app.modules.identity.tokens import create_team_invite_token

router = APIRouter(prefix="/identity", tags=["identity"])
logger = logging.getLogger(__name__)
_admin = Depends(require_role(Role.admin))


def _display_name(u: User) -> str:
    """A human-readable name derived from the email local part: split on '.', '_' and '-',
    title-case each token and join with spaces (e.g. "ronan.bolger" -> "Ronan Bolger").
    Falls back to the id when there is no email."""
    if not u.email:
        return u.id
    local = u.email.split("@")[0]
    tokens = [t for t in local.replace("_", ".").replace("-", ".").split(".") if t]
    name = " ".join(t[:1].upper() + t[1:] for t in tokens)
    return name or local


def _user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": _display_name(u),
            "role": u.role.value, "role_label": ROLE_LABELS.get(u.role, u.role.value),
            "status": "accepted", "is_owner": u.role is Role.owner}


def _assert_assignable(role: Role) -> None:
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=400, detail="role must be one of: User, Creator, Admin")


async def _get_tenant_user(user_id: str, tenant: str, store: UserStore) -> User:
    user = await store.get_by_id(user_id)
    if user is None or user.tenant != tenant:
        raise HTTPException(status_code=404, detail="user not found")
    return user


class InviteBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role = Role.viewer


class RoleBody(BaseModel):
    role: Role


@router.get("/users")
async def list_users(tenant: str = Depends(authed_tenant), store: UserStore = Depends(get_store),
                     pending: PendingInviteStore = Depends(get_pending_invites)) -> dict:
    """The tenant's users (Accepted) plus outstanding invites (Pending). Read-open to any
    authenticated member of the tenant."""
    users = [_user_dict(u) for u in await store.list_by_tenant(tenant)]
    users.sort(key=lambda u: u["email"])
    invites = [{"email": i.email, "role": i.role.value,
                "role_label": ROLE_LABELS.get(i.role, i.role.value),
                "status": "pending", "invited_at": i.invited_at}
               for i in await pending.list(tenant)]
    return {"users": users, "pending": invites}


@router.post("/users/invite")
async def invite_user(
    body: InviteBody,
    tenant: str = Depends(authed_tenant),
    claims: dict = _admin,
    store: UserStore = Depends(get_store),
    pending: PendingInviteStore = Depends(get_pending_invites),
    email_sender: EmailSender = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Record a pending role and email signup guidance. Owner/admin only."""
    _assert_assignable(body.role)
    email = body.email.strip().lower()
    existing = await store.get_by_email(email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="a user with that email already exists")
    if await pending.get(tenant, email) is not None:
        raise HTTPException(status_code=409, detail="an invitation for that email is already pending")

    invite = await pending.add(tenant, email, body.role)
    invite_token = create_team_invite_token(
        tenant=tenant, email=invite.email, role=invite.role.value,
        invite_version=int(invite.invited_at * 1_000_000))
    signup_url = f"{settings.public_base_url.rstrip('/')}/signup?{urlencode({'invite': invite_token})}"
    subject, text_body, html_body = team_invite_email(
        signup_url=signup_url,
        invited_email=invite.email,
        role_label=ROLE_LABELS.get(invite.role, invite.role.value),
        workspace=tenant,
        inviter_email=claims.get("email"),
    )
    try:
        sent = await run_in_threadpool(
            email_sender.send,
            to=invite.email,
            subject=subject,
            body=text_body,
            html=html_body,
        )
    except Exception as exc:
        await pending.remove(tenant, email)
        logger.warning("transactional_email_failed", extra={"flow": "team_invite", "tenant": tenant})
        raise HTTPException(
            status_code=503,
            detail="invitation email could not be sent; please try again",
        ) from exc
    if not sent:
        await pending.remove(tenant, email)
        logger.warning("transactional_email_failed", extra={"flow": "team_invite", "tenant": tenant})
        raise HTTPException(
            status_code=503,
            detail="invitation email could not be sent; please try again",
        )
    return {"email": invite.email, "role": invite.role.value,
            "role_label": ROLE_LABELS.get(invite.role, invite.role.value),
            "status": "pending", "invited_at": invite.invited_at}


@router.put("/users/{user_id}/role")
async def update_role(user_id: str, body: RoleBody, tenant: str = Depends(authed_tenant),
                      _r: dict = _admin, store: UserStore = Depends(get_store)) -> dict:
    """Change a member's role. owner/admin only. The account owner's role is protected and the
    owner role is never assignable (so the last owner can't be demoted away)."""
    _assert_assignable(body.role)
    user = await _get_tenant_user(user_id, tenant, store)
    if user.role is Role.owner:
        raise HTTPException(status_code=400, detail="cannot change the owner's role")
    await store.set_role(user_id, body.role)
    updated = await store.get_by_id(user_id)
    return _user_dict(updated) if updated else _user_dict(user)


@router.delete("/users/{user_id}")
async def remove_user(user_id: str, tenant: str = Depends(authed_tenant), _r: dict = _admin,
                      store: UserStore = Depends(get_store)) -> dict:
    """Remove a member from the tenant. owner/admin only. The account owner can never be removed
    (protects the last owner / sole-owner-removing-themselves)."""
    user = await _get_tenant_user(user_id, tenant, store)
    if user.role is Role.owner:
        raise HTTPException(status_code=400, detail="cannot remove the owner")
    await store.delete(user_id)
    return {"removed": user_id}


@router.delete("/users/pending/{email}")
async def cancel_invite(email: str, tenant: str = Depends(authed_tenant), _r: dict = _admin,
                        pending: PendingInviteStore = Depends(get_pending_invites)) -> dict:
    """Cancel a still-pending invite. owner/admin only."""
    if not await pending.remove(tenant, email):
        raise HTTPException(status_code=404, detail="invite not found")
    return {"removed": email.lower()}
