"""Test helpers for authenticated requests."""
from app.modules.identity.tokens import create_access_token


def auth_cookies(tenant: str = "acme", role: str = "owner", user_id: str = "u-test") -> dict:
    """A cookie dict carrying a valid access token for the given tenant/role."""
    return {"qiko_access": create_access_token(user_id, tenant=tenant, role=role, sid="s1")}
