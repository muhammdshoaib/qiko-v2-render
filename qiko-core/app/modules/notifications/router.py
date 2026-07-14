"""Generic in-app notification inbox API -- tenant-scoped equivalent of the qiko-backend
origin/idg-sales notification endpoints (notifications / read / read-all), generalised so any
vertical can reuse it. All endpoints are tenant-scoped via `authed_tenant` (BOLA-safe: tenant +
recipient user come from the verified access-token claims, never a client-supplied value)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.deps import authed_tenant, current_claims

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notifications(request: Request):
    return request.app.state.notifications


def _user_id(claims: dict) -> str | None:
    return claims.get("sub") or claims.get("user_id")


def _out(n) -> dict:
    return {
        "id": n.id, "category": n.category, "type": n.type, "title": n.title, "body": n.body,
        "agentId": n.agent_id, "opportunityId": n.opportunity_id, "metadata": n.metadata,
        "read": n.is_read(), "readAt": n.read_at, "createdAt": n.created_at,
    }


@router.get("")
async def list_notifications(category: str | None = None, unread_only: bool = False, limit: int = 50,
                             tenant: str = Depends(authed_tenant), claims: dict = Depends(current_claims),
                             svc=Depends(get_notifications)) -> dict:
    items = await svc.list(tenant, _user_id(claims), category=category, unread_only=unread_only,
                           limit=max(1, min(200, limit)))
    unread = await svc.unread_count(tenant, _user_id(claims), category=category)
    return {"notifications": [_out(n) for n in items], "unreadCount": unread}


@router.get("/unread-count")
async def unread_count(category: str | None = None, tenant: str = Depends(authed_tenant),
                       claims: dict = Depends(current_claims), svc=Depends(get_notifications)) -> dict:
    return {"unreadCount": await svc.unread_count(tenant, _user_id(claims), category=category)}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, tenant: str = Depends(authed_tenant),
                    claims: dict = Depends(current_claims), svc=Depends(get_notifications)) -> dict:
    n = await svc.mark_read(tenant, notification_id, _user_id(claims))
    if n is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"notification": _out(n)}


@router.post("/read-all")
async def mark_all_read(category: str | None = None, tenant: str = Depends(authed_tenant),
                        claims: dict = Depends(current_claims), svc=Depends(get_notifications)) -> dict:
    updated = await svc.mark_all_read(tenant, _user_id(claims), category=category)
    return {"updated": updated}
