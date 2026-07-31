"""R2 Leg 5b - generic HTTP connector + SSRF guard (deterministic; no real network).

The generic connector fetches a user-supplied config.url, so the SSRF guard is the critical control.
All HTTP is served by an httpx MockTransport and DNS is a stub resolver, so these tests are hermetic.
"""
from __future__ import annotations

import socket

import httpx
import pytest

from app.modules.sales_intelligence.connectors import GenericHttpNoticeConnector
from app.modules.sales_intelligence.ssrf import SsrfError, assert_public_url


def _resolver_to(ip: str):
    def _resolve(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    return _resolve


PUBLIC = _resolver_to("93.184.216.34")
PRIVATE = _resolver_to("10.0.0.5")

# Ingest-filter bypass (mirrors the merged default filter) so parsing tests are isolated from
# the country/category allowlist. The scan flow passes these via merge_ingest_filter.
_BYPASS = {"country_allowlist": "*", "category_allowlist": "*"}


# --- SSRF guard ---
def test_ssrf_blocks_non_http_scheme():
    for url in ("file:///etc/passwd", "ftp://example.com/x", "gopher://x"):
        with pytest.raises(SsrfError):
            assert_public_url(url, resolver=PUBLIC)


def test_ssrf_blocks_loopback_private_and_metadata_literals():
    for url in ("http://127.0.0.1/x", "http://10.0.0.5/x", "http://192.168.1.1/x",
                "http://169.254.169.254/latest/meta-data/", "http://[::1]/x"):
        with pytest.raises(SsrfError):
            assert_public_url(url, resolver=PUBLIC)


def test_ssrf_blocks_hostname_resolving_to_private():
    with pytest.raises(SsrfError):
        assert_public_url("https://internal.corp/x", resolver=PRIVATE)


def test_ssrf_allows_public():
    addrs = assert_public_url("https://portal.example/search", resolver=PUBLIC)
    assert "93.184.216.34" in addrs


# --- connector parsing (MockTransport) ---
def _connector(handler, resolver=PUBLIC) -> GenericHttpNoticeConnector:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return GenericHttpNoticeConnector(client=client, resolver=resolver)


def test_generic_parses_json_notices():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"},
                              json={"results": [
                                  {"title": "Security guarding services", "url": "/n/1", "company": "MoD"},
                                  {"name": "Perimeter fencing", "link": "https://portal.example/n/2"},
                              ]})
    out = _connector(handler).search(_BYPASS, {"url": "https://portal.example/search"})
    titles = [n["title"] for n in out["notices"]]
    assert "Security guarding services" in titles and "Perimeter fencing" in titles
    n1 = next(n for n in out["notices"] if n["title"].startswith("Security"))
    assert n1["source_url"] == "https://portal.example/n/1" and n1["buyer"] == "MoD"


def test_generic_parses_rss_feed():
    rss = ("<?xml version='1.0'?><rss><channel>"
           "<item><title>Guard contract</title><link>https://portal.example/a</link></item>"
           "<item><title>Cleaning</title><link>https://portal.example/b</link></item>"
           "</channel></rss>")
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text=rss)
    out = _connector(handler).search(_BYPASS, {"url": "https://portal.example/feed"})
    assert {n["title"] for n in out["notices"]} == {"Guard contract", "Cleaning"}


def test_generic_parses_html_anchors():
    html_body = ("<html><body>"
                 "<a href='/tender/1'>Static security guarding services tender</a>"
                 "<a href='/x'>short</a>"  # too short -> ignored
                 "</body></html>")
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html_body)
    out = _connector(handler).search(_BYPASS, {"url": "https://portal.example/search"})
    assert len(out["notices"]) == 1
    assert out["notices"][0]["source_url"] == "https://portal.example/tender/1"


def test_generic_refuses_blocked_url_before_fetch():
    called = {"n": 0}
    def handler(request):
        called["n"] += 1
        return httpx.Response(200, text="{}")
    conn = _connector(handler, resolver=PRIVATE)
    with pytest.raises(SsrfError):
        conn.search({}, {"url": "https://internal.corp/search"})
    assert called["n"] == 0  # never fetched


def test_generic_keyword_filters_when_not_in_url():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"},
                              json=[{"title": "Security guarding", "url": "/1"},
                                    {"title": "Catering services", "url": "/2"}])
    out = _connector(handler).search({**_BYPASS, "query": "security"}, {"url": "https://portal.example/list"})
    assert [n["title"] for n in out["notices"]] == ["Security guarding"]


def test_generic_requires_url():
    with pytest.raises(ValueError):
        _connector(lambda r: httpx.Response(200, text="{}")).search({}, {})


# --- service + scheduler integration (custom generic source actually scans) ---
def _build_service_with_generic(handler):
    from app.modules.notifications.service import NotificationService
    from app.modules.sales_intelligence.models import (
        InMemoryActivityLogStore,
        InMemoryIngestionSourceStore,
        InMemoryOpportunityStore,
    )
    from app.modules.sales_intelligence.notifications import SalesNotificationService
    from app.modules.sales_intelligence.service import OpportunityService

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return OpportunityService(
        scan_interval_minutes=1,
        generic=GenericHttpNoticeConnector(client=client, resolver=PUBLIC),
        sources=InMemoryIngestionSourceStore(), opportunities=InMemoryOpportunityStore(),
        activity_logs=InMemoryActivityLogStore(),
        notifier=SalesNotificationService(notifications=NotificationService()),
    )


@pytest.mark.asyncio
async def test_scan_source_generic_creates_opportunities():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"},
                              json=[{"title": "Static guarding services", "url": "https://portal.example/n/9",
                                     "company": "City Council"}])
    svc = _build_service_with_generic(handler)
    # Attach a custom (generic) source and activate it.
    await svc.attach_source("acme", "ag1", "acme-portal", name="Acme Portal",
                            config_input={"url": "https://portal.example/search"})
    await svc.update_source_status("acme", "ag1", "acme-portal", "active")
    result = await svc.scan_source("acme", "ag1", "acme-portal",
                                   {"country_allowlist": "*", "category_allowlist": "*"})
    assert result["created"] == 1
    opps = await svc.opportunities.list_for_agent("acme", "ag1")
    assert len(opps) == 1 and opps[0].title == "Static guarding services"
    assert opps[0].source_key == "acme-portal"


@pytest.mark.asyncio
async def test_scan_source_rejects_ssrf_target():
    svc = _build_service_with_generic(lambda r: httpx.Response(200, text="[]"))
    svc.generic.resolver = PRIVATE  # custom source URL resolves to a private IP
    await svc.attach_source("acme", "ag1", "evil", name="Evil", config_input={"url": "https://internal.corp/x"})
    await svc.update_source_status("acme", "ag1", "evil", "active")
    # The scan surfaces the SSRF block as a scan failure (SalesIntelligenceError family).
    from app.modules.sales_intelligence.service import SalesIntelligenceError
    with pytest.raises((SsrfError, SalesIntelligenceError)):
        await svc.scan_source("acme", "ag1", "evil", {"country_allowlist": "*", "category_allowlist": "*"})
