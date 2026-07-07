import pytest

from app.modules.identity.admin_rbac import (
    AdminAuthzError,
    AdminOrg,
    AdminRole,
    can_invite_admins,
)


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
