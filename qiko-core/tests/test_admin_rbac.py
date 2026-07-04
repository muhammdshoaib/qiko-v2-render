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


def test_only_super_admin_can_invite_and_remove():
    org = AdminOrg()
    org.bootstrap_super_admin("boss@x.com")
    token = org.invite("boss@x.com", "viewer@x.com", AdminRole.viewer)
    assert org.accept(token) is AdminRole.viewer
    assert org.role_of("viewer@x.com") is AdminRole.viewer

    # a viewer cannot invite or remove
    with pytest.raises(AdminAuthzError):
        org.invite("viewer@x.com", "x@x.com", AdminRole.viewer)
    with pytest.raises(AdminAuthzError):
        org.remove("viewer@x.com", "boss@x.com")

    org.remove("boss@x.com", "viewer@x.com")
    assert org.role_of("viewer@x.com") is None


def test_invalid_invite_rejected():
    org = AdminOrg()
    with pytest.raises(AdminAuthzError):
        org.accept("not-a-token")
