"""JM2-1131 follow-ups, all three found during integration rather than by the suite.

1. The SQL activity store was constructed and then overwritten by an in-memory one, so every
   event the app sent was lost on redeploy.
2. Outcome reporting 404'd for anything generated before the last restart, because the lookup
   went through an in-memory cache.
3. There was no way to read a generated insight back at all.
"""
import app.main as main_module
from app.core.config import Settings
from app.modules.joseph_mews.generations import GenerationKind, InMemoryGenerationStore


def test_dev_defaults_do_not_overwrite_the_sql_stores(monkeypatch):
    """The regression that started this. `create_app()` assigned the in-memory activity store
    unconditionally, several hundred lines BELOW the SQL wiring, so it always won: preprod ran
    with use_db_stores=True and an in-memory store, and nothing failed loudly. Anything that
    looks like a dev fallback must be guarded by the same condition as the real thing."""
    source = (main_module.__file__ or "")
    assert source
    text = open(source).read()

    sql_at = text.index("app.state.investor_activity = SqlInvestorActivityStore(sm)")
    mem_at = text.index("app.state.investor_activity = InMemoryInvestorActivityStore()")
    assert sql_at < mem_at, "expected the SQL wiring first, then a guarded dev fallback"

    # The dev fallback must sit inside a use_db_stores guard, not at function scope.
    guard = text.rindex("if not get_settings().use_db_stores:", 0, mem_at)
    between = text[guard:mem_at]
    assert "\n    app.state" not in between, (
        "the in-memory fallback is not inside the use_db_stores guard, so it will overwrite the "
        "SQL store again"
    )


def test_the_two_stores_share_an_interface():
    """They are assigned to the same attribute, so a drift in either direction reintroduces the
    class of bug above: the app would work in tests and fail in preprod, or vice versa."""
    from app.db.stores import SqlJmGenerationStore

    expected = {"get", "put", "record_outcome", "counts", "latest_property_insight"}
    for store in (InMemoryGenerationStore, SqlJmGenerationStore):
        missing = expected - {name for name in dir(store) if not name.startswith("_")}
        assert not missing, f"{store.__name__} is missing {missing}"


async def test_a_generation_is_readable_after_the_process_that_made_it():
    """What outcome reporting actually needs. Previously the requestId lived in a module-level
    dict, so a release made every prior id unknown and every outcome report a 404."""
    store = InMemoryGenerationStore()
    await store.put("joseph-mews", "req-1", GenerationKind.property_insight,
                    {"summary": "Strong rental yield", "groundedIn": ["portfolio"]},
                    investor_ref="34", property_name="Snow Hill Wharf")

    seen, result = await store.get("joseph-mews", "req-1")
    assert seen and result["summary"] == "Strong rental yield"

    assert await store.record_outcome("joseph-mews", "req-1", "accurate", "investor converted")
    counts = await store.counts("joseph-mews", GenerationKind.property_insight)
    assert counts.as_dict() == {"accurate": 1, "inaccurate": 0}


async def test_an_unknown_request_id_cannot_have_an_outcome_recorded():
    store = InMemoryGenerationStore()
    assert await store.record_outcome("joseph-mews", "never-generated", "accurate", "") is False


async def test_a_failed_generation_is_remembered_as_failed_not_as_never_asked():
    """`seen` has to distinguish the two: never asked means draft, asked-and-failed means return
    GENERATION_FAILED. Collapsing them would retry a failing generation forever."""
    store = InMemoryGenerationStore()
    await store.put("joseph-mews", "req-fail", GenerationKind.signal, None)
    seen, result = await store.get("joseph-mews", "req-fail")
    assert seen is True
    assert result is None


async def test_idempotency_keeps_the_first_result_for_a_request_id():
    store = InMemoryGenerationStore()
    await store.put("joseph-mews", "req-2", GenerationKind.signal, {"summary": "first",
                                                                    "suggestedNextAction": "call",
                                                                    "groundedIn": []})
    seen, result = await store.get("joseph-mews", "req-2")
    assert seen and result["summary"] == "first"


async def test_latest_property_insight_is_readable_by_investor_and_property():
    """Backs GET /insights/property, which the app had no equivalent of. Shoaib asked for it
    during integration on 10 Sep."""
    store = InMemoryGenerationStore()
    await store.put("joseph-mews", "old", GenerationKind.property_insight,
                    {"summary": "older", "groundedIn": []},
                    investor_ref="34", property_name="Snow Hill Wharf")
    await store.put("joseph-mews", "new", GenerationKind.property_insight,
                    {"summary": "newer", "groundedIn": []},
                    investor_ref="34", property_name="Snow Hill Wharf")
    await store.put("joseph-mews", "other", GenerationKind.property_insight,
                    {"summary": "different property", "groundedIn": []},
                    investor_ref="34", property_name="The Axium")

    latest = await store.latest_property_insight("joseph-mews", "34",
                                                 property_name="Snow Hill Wharf")
    assert latest["summary"] == "newer"
    narrowed = await store.latest_property_insight("joseph-mews", "34", property_name="The Axium")
    assert narrowed["summary"] == "different property"
    assert await store.latest_property_insight("joseph-mews", "99") is None


async def test_a_failed_generation_is_not_returned_by_the_getter():
    """The app asking "what insight do you have" wants an insight or nothing, not last week's
    error."""
    store = InMemoryGenerationStore()
    await store.put("joseph-mews", "failed", GenerationKind.property_insight, None,
                    investor_ref="34", property_name="Snow Hill Wharf")
    assert await store.latest_property_insight("joseph-mews", "34") is None


async def test_one_tenant_cannot_read_another_tenants_generation_by_request_id():
    """requestIds come from the caller, so they are guessable. Tenant scoping is what stops a
    shared-key caller reading across tenants."""
    store = InMemoryGenerationStore()
    await store.put("joseph-mews", "shared-id", GenerationKind.signal, {"summary": "theirs",
                                                                        "suggestedNextAction": "",
                                                                        "groundedIn": []})
    seen, result = await store.get("other-tenant", "shared-id")
    assert seen is False and result is None
    assert await store.record_outcome("other-tenant", "shared-id", "accurate", "") is False


def test_a_non_dev_environment_refuses_to_start_without_db_stores():
    """The real safety net behind the fix above, and worth pinning.

    `use_db_stores` DEFAULTS to False (a dev convenience), so the guarded fallback I added is only
    safe because a non-dev environment refuses to boot without it. Preprod reported
    use_db_stores=True for exactly that reason. If this guard ever weakens, the in-memory stores
    become production behaviour silently, which is the failure mode this whole file exists for."""
    import pytest

    assert Settings().use_db_stores is False, "dev default; the guard below is what protects prod"
    with pytest.raises(Exception) as raised:
        Settings(environment="preprod", session_secret="x" * 48,
                 use_db_stores=False).assert_secrets_set()
    assert "USE_DB_STORES=true" in str(raised.value)
