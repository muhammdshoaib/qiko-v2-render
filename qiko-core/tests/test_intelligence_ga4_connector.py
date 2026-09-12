from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.modules.intelligence.connectors import GA4Connector

# GA4Client._client() returns an injected httpx.Client verbatim (it does not layer base_url onto
# it, see app.integrations.clients._client), so an injected test client must carry the real GA4
# base_url itself, exactly like tests/test_integration_clients.py's GA4Client coverage does.
_GA4_BASE_URL = "https://analyticsdata.googleapis.com/v1beta"


def _stub_global_property(monkeypatch) -> None:
    """GA4Connector no longer accepts a per-agent property override (A01/BOLA fix): it always
    resolves the property from Settings.ga4_property_id, exactly like the access token. So any
    test exercising a real run_report call needs the global setting stubbed, the same way the
    router's own tests stub it (see test_intelligence_router.py's
    test_ga4_is_globally_configured_once_settings_are_set)."""
    monkeypatch.setattr(get_settings(), "ga4_property_id", "123456789")


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=_GA4_BASE_URL)


def _ga4_response(rows: list[tuple[str, str, str]]) -> dict:
    """rows: list of (date, sessions, activeUsers) as GA4 returns them (date = YYYYMMDD)."""
    return {
        "dimensionHeaders": [{"name": "date"}],
        "metricHeaders": [{"name": "sessions"}, {"name": "activeUsers"}],
        "rows": [
            {"dimensionValues": [{"value": d}],
             "metricValues": [{"value": s}, {"value": a}]}
            for d, s, a in rows
        ],
    }


async def test_fetch_since_emits_one_signal_per_day_in_the_window(monkeypatch):
    _stub_global_property(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ga4_response([
            ("20260909", "120", "80"),
            ("20260910", "150", "95"),
        ]))

    connector = GA4Connector(http_client=_mock_client(handler))
    since = datetime(2026, 9, 8, tzinfo=timezone.utc)
    # No per-agent config: GA4 always resolves its property from Settings.ga4_property_id
    # (see GA4Connector._client), so `config` carries nothing here.
    signals = await connector.fetch_since(
        config={}, credential="", since=since,
        tenant="acme", agent_id="a1")

    assert len(signals) == 2
    assert {s.external_id for s in signals} == {"ga4-20260909", "ga4-20260910"}
    first = next(s for s in signals if s.external_id == "ga4-20260910")
    assert first.kind == "traffic_snapshot"
    assert "150" in first.title or "150" in first.body


async def test_verify_reports_ok_when_the_report_call_succeeds(monkeypatch):
    _stub_global_property(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ga4_response([("20260910", "1", "1")]))

    connector = GA4Connector(http_client=_mock_client(handler))
    result = await connector.verify(config={}, credential="")
    assert result["ok"] is True


async def test_verify_reports_an_error_when_the_report_call_fails(monkeypatch):
    _stub_global_property(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    connector = GA4Connector(http_client=_mock_client(handler))
    result = await connector.verify(config={}, credential="")
    assert result["ok"] is False


async def test_verify_ignores_a_property_id_in_config():
    """A caller-supplied config["property_id"] must have zero effect: GA4Connector._client always
    passes property_id=None to GA4Client. With no global Settings.ga4_property_id configured
    (the default in tests), the report call fails on the *global* setting being unset/blank,
    proving the config value was never consulted -- if it had been, this would have used
    "999999999" and succeeded against the handler below instead."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ga4_response([("20260910", "1", "1")]))

    connector = GA4Connector(http_client=_mock_client(handler))
    result = await connector.verify(config={"property_id": "999999999"}, credential="")
    assert result["ok"] is False
