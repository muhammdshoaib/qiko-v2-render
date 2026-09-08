import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlInvestorActivityStore


async def _sessionmaker(path: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "qiko.db")


async def test_record_and_list_roundtrip(db_path):
    sm, _ = await _sessionmaker(db_path)
    store = SqlInvestorActivityStore(sm)
    await store.record("joseph-mews", "inv-1", category="screen", label="Dashboard")
    events = await store.list_for_investor("joseph-mews", "inv-1")
    assert len(events) == 1
    assert events[0].category == "screen"
    assert events[0].label == "Dashboard"


async def test_property_visit_stores_name_location_postcode_only(db_path):
    sm, _ = await _sessionmaker(db_path)
    store = SqlInvestorActivityStore(sm)
    await store.record(
        "joseph-mews", "inv-1", category="property_visit", label="PropertyDetail",
        property_name="The Mayfair Residence", location="Mount Street, Mayfair", postcode="W1K 2HQ",
    )
    events = await store.list_for_investor("joseph-mews", "inv-1")
    assert events[0].property_name == "The Mayfair Residence"
    assert events[0].location == "Mount Street, Mayfair"
    assert events[0].postcode == "W1K 2HQ"


async def test_list_is_scoped_to_tenant_and_investor(db_path):
    sm, _ = await _sessionmaker(db_path)
    store = SqlInvestorActivityStore(sm)
    await store.record("joseph-mews", "inv-1", category="screen", label="Dashboard")
    await store.record("joseph-mews", "inv-2", category="screen", label="Explore")
    await store.record("other-tenant", "inv-1", category="screen", label="Overview")
    events = await store.list_for_investor("joseph-mews", "inv-1")
    assert len(events) == 1
    assert events[0].label == "Dashboard"


async def test_occurred_at_defaults_to_now_when_not_supplied(db_path):
    sm, _ = await _sessionmaker(db_path)
    store = SqlInvestorActivityStore(sm)
    await store.record("joseph-mews", "inv-1", category="screen", label="Dashboard")
    events = await store.list_for_investor("joseph-mews", "inv-1")
    assert events[0].occurred_at is not None
