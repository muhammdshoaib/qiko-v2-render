"""Test helpers for authenticated requests."""
import asyncio

from app.modules.agents.service import Agent
from app.modules.identity.tokens import create_access_token, decode_token


def auth_cookies(tenant: str = "acme", role: str = "owner", user_id: str = "u-test",
                 email: str | None = None, mfa: bool = True) -> dict:
    """A cookie dict carrying a valid access token for the given tenant/role. `email` matters
    only for platform-admin endpoints (see core.deps.require_platform_admin) -- the tenant role
    here never grants cross-tenant admin access, on purpose."""
    return {"qiko_access": create_access_token(user_id, tenant=tenant, role=role, sid="s1",
                                               email=email or f"{user_id}@test.local", mfa=mfa)}


def bootstrap_admin(client, email: str) -> None:
    """Sync bridge for seeding the (now async) AdminOrg registry from a sync test function."""
    asyncio.run(client.app.state.admin_org.bootstrap_super_admin(email))


def autoseed_rfp_pack_workers(client, monkeypatch) -> None:
    original = client.post

    def post(url, *args, **kwargs):
        if url == "/api/v1/rfp/packs":
            body, cookies = kwargs.get("json") or {}, kwargs.get("cookies") or {}
            token, agent_id = cookies.get("qiko_access"), body.get("agent_id")
            if token and agent_id:
                tenant = decode_token(token, expected_type="access")["tenant"]
                asyncio.run(client.app.state.agents.store.add(
                    Agent(id=agent_id, tenant=tenant, name=agent_id)))
        return original(url, *args, **kwargs)

    monkeypatch.setattr(client, "post", post)
