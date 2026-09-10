"""QIK-514: per-tenant and per-worker AI token/cost accounting.

Bedrock returns a usage block on every Converse call and Titan returns inputTextTokenCount, and both
were read for their text or vector and thrown away. So nothing in the platform could answer "what is
this customer costing us", which is the prerequisite for the cost dashboard, worker monitoring and
cost caps.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.tenancy import reset_tenant, set_tenant
from app.db.models import Base
from app.db.stores import SqlUsageStore
from app.modules.ai import usage
from app.modules.ai.bedrock import BedrockProvider
from app.modules.ai.embeddings import TitanEmbeddings


# --- pricing -------------------------------------------------------------------------------------

def test_the_geography_prefix_is_stripped_before_pricing():
    """BedrockProvider.model_id returns "eu.anthropic.claude-sonnet-4-5". A price table keyed on the
    prefixed form would never match, and every call would silently cost zero."""
    assert usage.base_model_id("eu.anthropic.claude-sonnet-4-5") == "anthropic.claude-sonnet-4-5"
    assert usage.base_model_id("us.anthropic.claude-sonnet-4-5") == "anthropic.claude-sonnet-4-5"
    assert usage.base_model_id("anthropic.claude-sonnet-4-5") == "anthropic.claude-sonnet-4-5"

    priced = usage.cost_nano_usd("eu.anthropic.claude-sonnet-4-5", 1000, 1000)
    assert priced == 3_000_000 + 15_000_000, "input and output are billed at different rates"
    assert usage.cost_nano_usd("anthropic.claude-sonnet-4-5", 1000, 1000) == priced


def test_a_date_qualified_model_id_is_still_priced():
    """Bedrock resolves the configured "anthropic.claude-sonnet-4-5" to
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0". A live check found exact matching failed on every
    real call and recorded it as unpriced with zero cost."""
    real = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert usage.rates_for(real) is not None
    assert usage.cost_nano_usd(real, 1000, 1000) == 3_000_000 + 15_000_000


def test_the_fast_tier_model_is_priced_not_silently_free():
    """Settings.bedrock_model_fast ("anthropic.claude-haiku-4-5", the Specialist's cheap/fast
    tier -- see app.tasks.jobs._fast_tier_worker) must have a rate in the price table. Checked
    against the SAME id shape BedrockProvider.model_id actually hands to usage.record(): the
    configured base model prefixed with the inference-profile geography (e.g. "eu."), not the
    bare model name, so a geography prefix on this new entry cannot silently defeat the match the
    way it did before rates_for() did prefix matching at all."""
    from app.core.config import get_settings
    from app.modules.ai.bedrock import BedrockProvider, resolve_model_id

    settings = get_settings()
    provider = BedrockProvider(model=settings.bedrock_model_fast)
    model_id = provider.model_id
    assert model_id == resolve_model_id(settings.bedrock_model_fast, settings.bedrock_inference_profile)
    # Pinned against the real configured default (an eu-prefixed inference profile) so this test
    # still catches a price-table key that only matches the bare, unprefixed model name.
    assert settings.bedrock_inference_profile == "eu" and model_id == "eu.anthropic.claude-haiku-4-5"

    rates = usage.rates_for(model_id)
    assert rates is not None, "the fast tier must not silently cost 0 / record priced=False"
    assert rates == {"input": 1_000_000, "output": 5_000_000}
    assert usage.cost_nano_usd(model_id, 1000, 1000) == 1_000_000 + 5_000_000


def test_the_longest_matching_prefix_wins():
    """Otherwise claude-3-5-haiku could be priced against a shorter claude-3 entry, i.e. at the wrong
    rate rather than at no rate, which is the harder error to notice."""
    haiku = usage.rates_for("anthropic.claude-3-5-haiku-20241022-v1:0")
    assert haiku is not None and haiku["input"] == 800_000
    older = usage.rates_for("anthropic.claude-3-haiku-20240307-v1:0")
    assert older is not None and older["input"] == 250_000


def test_a_small_embedding_is_not_rounded_away():
    """Titan is 20 micro-USD per 1,000 tokens, so in micro-USD an 8-token embed cost 0.16 and rounded
    to zero. An ingest embeds one chunk at a time, so a whole corpus would have looked free. Verified
    against live Bedrock, which recorded exactly that."""
    assert usage.cost_nano_usd("amazon.titan-embed-text-v2:0", 8, 0) == 160
    assert usage.cost_nano_usd("amazon.titan-embed-text-v2:0", 1, 0) == 20


def test_an_unknown_model_costs_zero_but_is_flagged_rather_than_hidden():
    """A missing rate must never break an answer, but unpriced spend must be visible or the total
    quietly understates reality."""
    assert usage.cost_nano_usd("some.new-model-v9", 5000, 5000) == 0

    token = set_tenant("acme")
    try:
        with usage.scope() as events:
            usage.record("some.new-model-v9", "generate", input_tokens=5000, output_tokens=5000)
            usage.record("anthropic.claude-sonnet-4-5", "generate", input_tokens=1000, output_tokens=0)
    finally:
        reset_tenant(token)

    totals = usage.accumulate(events)
    assert totals.calls == 2 and totals.unpriced_calls == 1
    assert totals.cost_nano_usd == 3_000_000


def test_cost_is_an_integer_so_it_cannot_drift():
    """Money is integer micro-USD everywhere. A float accumulating over millions of calls drifts."""
    value = usage.cost_nano_usd("anthropic.claude-sonnet-4-5", 1, 1)
    assert isinstance(value, int)


# --- attribution ---------------------------------------------------------------------------------

def test_an_event_is_attributed_to_whatever_tenant_and_worker_are_bound():
    tenant_token = set_tenant("acme")
    agent_token = usage.set_agent("w-1")
    try:
        with usage.scope() as events:
            usage.record("anthropic.claude-sonnet-4-5", "generate", input_tokens=10, output_tokens=5)
    finally:
        usage.reset_agent(agent_token)
        reset_tenant(tenant_token)

    assert len(events) == 1
    assert events[0].tenant == "acme" and events[0].agent_id == "w-1"
    assert events[0].input_tokens == 10 and events[0].output_tokens == 5


def test_unattributed_spend_is_recorded_not_dropped():
    """AWS has already billed the call. Losing it is worse than recording it as unattributed and
    attributing it later."""
    with usage.scope() as events:
        usage.record("anthropic.claude-sonnet-4-5", "generate", input_tokens=10, output_tokens=1)
    assert len(events) == 1 and events[0].tenant is None


def test_a_nested_scope_reuses_the_outer_list():
    """A job that opens a scope and then calls code which opens another must not have half its spend
    disappear into an inner list that nobody flushes."""
    with usage.scope() as outer:
        usage.record("anthropic.claude-sonnet-4-5", "generate", input_tokens=1, output_tokens=1)
        with usage.scope() as inner:
            usage.record("anthropic.claude-sonnet-4-5", "generate", input_tokens=2, output_tokens=2)
            assert inner is outer
    assert len(outer) == 2


def test_recording_outside_a_scope_warns_and_does_not_raise(caplog):
    with caplog.at_level("WARNING"):
        event = usage.record("anthropic.claude-sonnet-4-5", "generate", input_tokens=7)
    assert event.input_tokens == 7
    assert "outside a scope" in caplog.text


# --- the two chokepoints -------------------------------------------------------------------------

def test_bedrock_records_the_usage_block_it_used_to_discard(monkeypatch):
    class Client:
        def converse(self, **_kwargs):
            return {"output": {"message": {"content": [{"text": "ok"}]}},
                    "usage": {"inputTokens": 120, "outputTokens": 34, "totalTokens": 154}}

    provider = BedrockProvider()
    monkeypatch.setattr(provider, "_client", lambda: Client())
    token = set_tenant("acme")
    try:
        with usage.scope() as events:
            response = provider.generate("hello")
    finally:
        reset_tenant(token)

    assert response.input_tokens == 120 and response.output_tokens == 34
    assert len(events) == 1
    assert events[0].operation == "generate" and events[0].tenant == "acme"
    assert events[0].cost_nano_usd == (120 * 3_000_000 + 34 * 15_000_000) // 1000


def test_a_missing_usage_block_cannot_degrade_a_real_answer(monkeypatch):
    """FallbackProvider swallows any exception from the provider and returns a fabricated stub
    answer, so a shape surprise in the usage block must not raise."""
    class Client:
        def converse(self, **_kwargs):
            return {"output": {"message": {"content": [{"text": "still a real answer"}]}}}

    provider = BedrockProvider()
    monkeypatch.setattr(provider, "_client", lambda: Client())
    with usage.scope() as events:
        response = provider.generate("hello")

    assert response.text == "still a real answer"
    assert response.input_tokens == 0
    assert len(events) == 1 and events[0].input_tokens == 0


def test_titan_records_the_input_token_count_it_used_to_discard(monkeypatch):
    class Body:
        @staticmethod
        def read():
            import json

            return json.dumps({"embedding": [0.1] * 4, "inputTextTokenCount": 77})

    class Client:
        def invoke_model(self, **_kwargs):
            return {"body": Body()}

    import app.modules.ai.embeddings as embeddings_module

    monkeypatch.setattr(embeddings_module, "boto3", type("B", (), {"client": staticmethod(lambda **_k: Client())}),
                        raising=False)
    provider = TitanEmbeddings(dim=4)
    monkeypatch.setattr("boto3.client", lambda *_a, **_k: Client())

    with usage.scope() as events:
        vector = provider.embed("some text")

    assert len(vector) == 4
    assert len(events) == 1
    assert events[0].operation == "embed" and events[0].input_tokens == 77
    assert events[0].cost_nano_usd == 77 * 20_000 // 1000


# --- persistence and aggregation -----------------------------------------------------------------

def _store(tmp_path) -> tuple[SqlUsageStore, object]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'usage.db'}"
    engine = create_async_engine(url)

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create())
    return SqlUsageStore(async_sessionmaker(engine, expire_on_commit=False)), engine


def _event(tenant, agent, when, cost=1000, model="anthropic.claude-sonnet-4-5", priced=True):
    return usage.UsageEvent(tenant=tenant, agent_id=agent, model_id=model, operation="generate",
                            input_tokens=10, output_tokens=2, cost_nano_usd=cost,
                            created_at=when, priced=priced)


def test_totals_and_breakdowns_are_scoped_to_the_tenant(tmp_path):
    store, engine = _store(tmp_path)
    now = datetime.now(timezone.utc)

    async def scenario():
        await store.add_many([
            _event("acme", "w-1", now, cost=1000),
            _event("acme", "w-2", now, cost=2000),
            _event("acme", None, now, cost=500),
            _event("other", "w-9", now, cost=9999),
        ])
        totals = await store.totals("acme")
        by_agent = await store.totals_by_agent("acme")
        await engine.dispose()
        return totals, by_agent

    totals, by_agent = asyncio.run(scenario())
    assert totals.calls == 3 and totals.cost_nano_usd == 3500, "the other tenant must not leak in"
    assert set(by_agent) == {"w-1", "w-2", "unattributed"}
    assert by_agent["w-2"].cost_nano_usd == 2000
    assert by_agent["unattributed"].cost_nano_usd == 500


def test_a_date_window_bounds_the_totals(tmp_path):
    store, engine = _store(tmp_path)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=40)

    async def scenario():
        await store.add_many([_event("acme", "w-1", old, cost=7000),
                              _event("acme", "w-1", now, cost=1000)])
        recent = await store.totals("acme", start=now - timedelta(days=7))
        everything = await store.totals("acme")
        daily = await store.daily("acme")
        await engine.dispose()
        return recent, everything, daily

    recent, everything, daily = asyncio.run(scenario())
    assert recent.cost_nano_usd == 1000
    assert everything.cost_nano_usd == 8000
    assert set(daily) == {old.date().isoformat(), now.date().isoformat()}


def test_unpriced_calls_are_counted_in_the_durable_totals(tmp_path):
    store, engine = _store(tmp_path)
    now = datetime.now(timezone.utc)

    async def scenario():
        await store.add_many([_event("acme", "w-1", now, model="some.new-model", cost=0, priced=False),
                              _event("acme", "w-1", now)])
        totals = await store.totals("acme")
        await engine.dispose()
        return totals

    totals = asyncio.run(scenario())
    assert totals.calls == 2 and totals.unpriced_calls == 1


def test_a_flush_failure_never_reaches_the_caller():
    """Accounting must not be able to turn a served answer into a 500."""
    class Broken:
        async def add_many(self, _events):
            raise RuntimeError("database is down")

    event = _event("acme", "w-1", datetime.now(timezone.utc))
    asyncio.run(usage.flush(Broken(), [event]))  # must not raise


def test_the_usage_table_carries_the_indexes_the_dashboards_will_need():
    from app.db.models import AiUsageEvent

    names = {index.name for index in AiUsageEvent.__table__.indexes}
    assert "ix_ai_usage_tenant_created" in names
    assert "ix_ai_usage_tenant_agent_created" in names


def test_the_bulk_scripts_record_their_own_spend():
    """The re-embed and re-chunk tools each make thousands of Titan calls, the largest bursts this
    platform produces. Both previously ran with no scope open, so usage.record warned once per call and
    the spend went unrecorded: the very tooling built to fix the corpus was invisible to the cost view
    built alongside it. Pinned at the source, because exercising a whole-corpus rebuild in a unit test is
    not practical."""
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    for name in ("reembed_passages.py", "rechunk_oversized_passages.py"):
        source = (scripts / name).read_text()
        assert "usage.scope()" in source, f"{name} must open a usage scope"
        assert "usage.flush(" in source, f"{name} must persist what it recorded"
        assert "set_tenant(" in source, f"{name} must attribute spend to a tenant"
