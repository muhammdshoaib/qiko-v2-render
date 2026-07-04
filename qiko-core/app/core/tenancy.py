"""Request-scoped tenant context.

Multi-tenancy is first-class: every request carries a tenant id, and data-access code reads it
from here so queries are filtered centrally rather than by ad-hoc convention. This structurally
prevents the cross-tenant leak class of bug (see 01-current-state P2/P3).
"""
from __future__ import annotations

from contextvars import ContextVar

from fastapi import Header

_tenant: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def set_tenant(tenant_id: str | None) -> object:
    """Set the current tenant and return a token for later reset."""
    return _tenant.set(tenant_id)


def get_tenant() -> str | None:
    return _tenant.get()


def reset_tenant(token: object) -> None:
    _tenant.reset(token)  # type: ignore[arg-type]


def require_tenant() -> str:
    tenant = get_tenant()
    if not tenant:
        raise PermissionError("No tenant in context")
    return tenant


async def tenant_dependency(x_tenant_id: str | None = Header(default=None)) -> str | None:
    """FastAPI dependency that binds the tenant from the request header for the call."""
    token = set_tenant(x_tenant_id)
    try:
        yield x_tenant_id
    finally:
        reset_tenant(token)
