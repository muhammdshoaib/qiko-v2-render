"""Test helpers for authenticated requests."""
import asyncio

from app.modules.identity.tokens import create_access_token


def auth_cookies(tenant: str = "acme", role: str = "owner", user_id: str = "u-test",
                 email: str | None = None) -> dict:
    """A cookie dict carrying a valid access token for the given tenant/role. `email` matters
    only for platform-admin endpoints (see core.deps.require_platform_admin) -- the tenant role
    here never grants cross-tenant admin access, on purpose."""
    return {"qiko_access": create_access_token(user_id, tenant=tenant, role=role, sid="s1",
                                               email=email or f"{user_id}@test.local")}


def bootstrap_admin(client, email: str) -> None:
    """Sync bridge for seeding the (now async) AdminOrg registry from a sync test function."""
    asyncio.run(client.app.state.admin_org.bootstrap_super_admin(email))
