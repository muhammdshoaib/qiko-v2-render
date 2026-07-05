"""SqlUserStore satisfies the full UserStore protocol (add/get/set_sid/enable_twofa/set_password)."""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlUserStore
from app.modules.identity.rbac import Role
from app.modules.identity.security import hash_password
from app.modules.identity.store import User


async def _store(path) -> SqlUserStore:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlUserStore(async_sessionmaker(engine, expire_on_commit=False))


async def test_sql_user_store_add_creates_tenant_row_if_missing(tmp_path):
    """Regression: signup for a brand-new tenant must not violate the users.tenant_id FK."""
    from sqlalchemy import select

    from app.db.models import Tenant as TenantRow

    store = await _store(tmp_path / "t.db")
    await store.add(User(id="u1", email="new@tenant.co", password_hash=hash_password("pw"),
                         tenant="brand-new-tenant", role=Role.owner))
    async with store.sessionmaker() as s:
        row = (await s.execute(select(TenantRow).where(TenantRow.id == "brand-new-tenant"))).scalar_one_or_none()
    assert row is not None
    # adding a second user for the same (now-existing) tenant must not fail either
    await store.add(User(id="u2", email="second@tenant.co", password_hash=hash_password("pw"),
                         tenant="brand-new-tenant", role=Role.viewer))
    assert (await store.get_by_email("second@tenant.co")).id == "u2"


async def test_sql_user_store_full_lifecycle(tmp_path):
    store = await _store(tmp_path / "u.db")
    await store.add(User(id="u1", email="Owner@Qiko.ai", password_hash=hash_password("pw"),
                         tenant="acme", role=Role.owner))
    assert (await store.get_by_email("owner@qiko.ai")).id == "u1"
    await store.set_sid("u1", "sid-1")
    assert (await store.get_by_id("u1")).current_sid == "sid-1"
    await store.enable_twofa("u1", "SECRET123")
    u = await store.get_by_id("u1")
    assert u.twofa_enabled is True and u.totp_secret == "SECRET123"
    await store.set_password("u1", "new-hash")
    assert (await store.get_by_id("u1")).password_hash == "new-hash"
