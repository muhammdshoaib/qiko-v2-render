"""SqlUserStore satisfies the full UserStore protocol (add/get/set_sid/enable_twofa/set_password)."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.config import get_settings
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
    await store.add(User(id="u1", email="new@invalid", password_hash=hash_password("pw"),
                         tenant="brand-new-tenant", role=Role.owner))
    async with store.sessionmaker() as s:
        row = (await s.execute(select(TenantRow).where(TenantRow.id == "brand-new-tenant"))).scalar_one_or_none()
    assert row is not None
    # adding a second user for the same (now-existing) tenant must not fail either
    await store.add(User(id="u2", email="second@invalid", password_hash=hash_password("pw"),
                         tenant="brand-new-tenant", role=Role.viewer))
    assert (await store.get_by_email("second@invalid")).id == "u2"


async def test_sql_user_store_full_lifecycle(tmp_path):
    store = await _store(tmp_path / "u.db")
    await store.add(User(id="u1", email="Owner@invalid", password_hash=hash_password("pw"),
                         tenant="acme", role=Role.owner))
    assert (await store.get_by_email("owner@invalid")).id == "u1"
    await store.set_sid("u1", "sid-1")
    assert (await store.get_by_id("u1")).current_sid == "sid-1"
    await store.enable_twofa("u1", "SECRET123")
    u = await store.get_by_id("u1")
    assert u.twofa_enabled is True and u.totp_secret == "SECRET123"
    from app.db.models import User as UserRow
    async with store.sessionmaker() as session:
        row = await session.get(UserRow, "u1")
    assert row.totp_secret.startswith("enc:") and "SECRET123" not in row.totp_secret
    await store.set_password("u1", "new-hash")
    assert (await store.get_by_id("u1")).password_hash == "new-hash"


async def test_shared_claims_rejects_revoked_db_session(tmp_path, monkeypatch):
    store = await _store(tmp_path / "sid.db")
    await store.add(User(
        id="u1", email="owner@invalid", password_hash=hash_password("pw"),
        tenant="acme", role=Role.owner, current_sid="sid-1",
    ))
    settings = get_settings()
    monkeypatch.setattr(settings, "use_db_stores", True)
    monkeypatch.setattr(deps, "get_user_store", lambda: store)
    from app.modules.identity.tokens import create_access_token

    token = create_access_token(
        "u1", tenant="acme", role="owner", sid="sid-1", email="owner@invalid"
    )
    request = SimpleNamespace(cookies={"qiko_access": token})
    claims = await deps.current_claims(request)
    assert claims["sub"] == "u1"

    await store.set_sid("u1", "sid-2")
    with pytest.raises(HTTPException) as error:
        await deps.current_claims(request)
    assert error.value.status_code == 401
