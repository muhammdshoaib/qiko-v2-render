import pytest

from app.core import tenancy


def test_set_get_reset():
    assert tenancy.get_tenant() is None
    token = tenancy.set_tenant("acme")
    assert tenancy.get_tenant() == "acme"
    tenancy.reset_tenant(token)
    assert tenancy.get_tenant() is None


def test_require_tenant_success():
    token = tenancy.set_tenant("acme")
    try:
        assert tenancy.require_tenant() == "acme"
    finally:
        tenancy.reset_tenant(token)


def test_require_tenant_raises_without_tenant():
    with pytest.raises(PermissionError):
        tenancy.require_tenant()


async def test_tenant_dependency_binds_and_resets():
    gen = tenancy.tenant_dependency(x_tenant_id="beta")
    value = await gen.__anext__()
    assert value == "beta"
    assert tenancy.get_tenant() == "beta"
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    assert tenancy.get_tenant() is None
