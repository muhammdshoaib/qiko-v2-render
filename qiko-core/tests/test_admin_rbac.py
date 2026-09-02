import pytest

from app.modules.identity.admin_rbac import (
    AdminAuthzError,
    AdminOrg,
    AdminRole,
    Capability,
    can_invite_admins,
    default_capabilities,
)
from app.modules.identity.tokens import create_team_invite_token


def test_capabilities():
    assert can_invite_admins(AdminRole.super_admin) is True
    assert can_invite_admins(AdminRole.viewer) is False


async def test_only_super_admin_can_invite_and_remove():
    org = AdminOrg()
    await org.bootstrap_super_admin("boss@x.com")
    token = await org.invite("boss@x.com", "viewer@x.com", AdminRole.viewer)
    assert await org.accept(token) is AdminRole.viewer
    assert await org.role_of("viewer@x.com") is AdminRole.viewer

    # a viewer cannot invite or remove
    with pytest.raises(AdminAuthzError):
        await org.invite("viewer@x.com", "x@x.com", AdminRole.viewer)
    with pytest.raises(AdminAuthzError):
        await org.remove("viewer@x.com", "boss@x.com")

    await org.remove("boss@x.com", "viewer@x.com")
    assert await org.role_of("viewer@x.com") is None


async def test_invalid_invite_rejected():
    org = AdminOrg()
    with pytest.raises(AdminAuthzError):
        await org.accept("not-a-token")


async def test_team_invite_token_cannot_be_accepted_as_platform_admin():
    org = AdminOrg()
    token = create_team_invite_token(
        tenant="tenant-a", email="person@example.com", role="viewer", invite_version=1)

    with pytest.raises(AdminAuthzError):
        await org.accept(token)

    assert await org.role_of("person@example.com") is None


def test_support_view_worker_is_super_admin_default_but_not_viewer_default():
    assert Capability.support_view_worker in default_capabilities(AdminRole.super_admin)
    assert Capability.support_view_worker not in default_capabilities(AdminRole.viewer)
