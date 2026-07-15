from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.modules.sales_intelligence.category_matcher import SecurityCategoryMatcher
from app.modules.sales_intelligence.connectors import TedCountryResolver, TedNoticeConnector, UngmNoticeConnector
from app.modules.sales_intelligence.ingest_filter import IngestFilter
from app.modules.sales_intelligence.qualification import QualificationService
from app.modules.sales_intelligence.salesforce import SalesforceAuthService, SalesforceError, SalesforcePushService
from app.modules.sales_intelligence.service import OpportunityMutationService, OpportunityService, SourceInactiveError
from app.modules.sales_intelligence.target_countries import TargetCountries

from tests.helpers import auth_cookies


# --- qualification (deterministic scorer) ---
def test_qualification_bids_on_strong_security_fit_in_target_country():
    svc = QualificationService()
    result = svc.qualify({
        "title": "Provision of static security guarding services",
        "category": "Security services",
        "country": "United Arab Emirates",
        "buyer": "Ministry of Interior",
        "estimated_value": 500000,
        "deadline_at": datetime.now(timezone.utc) + timedelta(days=45),
    })
    assert result["recommendation"] == "Bid"
    assert result["stage"] == "qualified"
    assert result["qualification_score"] >= 75


def test_qualification_no_bids_on_zero_service_alignment():
    svc = QualificationService()
    result = svc.qualify({"title": "Supply of office stationery", "category": "Stationery",
                          "country": "France", "buyer": "City Council"})
    assert result["recommendation"] == "No Bid"
    assert result["stage"] == "rejected"


def test_qualification_flags_missing_fields_and_routes_to_review():
    svc = QualificationService()
    result = svc.qualify({"title": "Security guarding and risk protection services"})
    assert "country" in result["missing_fields"]
    assert "buyer" in result["missing_fields"]
    assert result["recommendation"] in ("Review", "No Bid")


def test_qualification_dimensions_present():
    svc = QualificationService()
    result = svc.qualify({"title": "CCTV surveillance and access control system", "category": "Security",
                          "country": "Kenya", "buyer": "Buyer", "estimated_value": 1000})
    dims = result["qualification_dimensions"]
    for key in ("serviceMatch", "geography", "industry", "technology", "securityClearance",
               "framework", "contractValue", "deadline", "strategicCustomer"):
        assert key in dims


# --- target countries / category matcher / ingest filter ---
def test_target_countries_matches_alias_substring():
    tc = TargetCountries()
    assert tc.matches("United Arab Emirates")
    assert tc.matches("uae")
    assert not tc.matches("France")
    assert not tc.matches(None)


def test_security_category_matcher_rejects_bundled_services():
    matcher = SecurityCategoryMatcher()
    assert matcher.matches({"title": "Static security guarding services", "category": "Security"})
    assert not matcher.matches({"title": "Cleaning and security services bundle"})
    assert not matcher.matches({"title": "Office furniture supply"})


def test_security_category_matcher_matches_cpv_prefix():
    matcher = SecurityCategoryMatcher()
    notice = {"title": "Unrelated title", "raw": {"classification-cpv": "79710000-4"}}
    assert matcher.matches(notice)


def test_ingest_filter_rejects_out_of_target_country():
    f = IngestFilter()
    notice = {"title": "Security guarding services", "category": "Security", "country": "France"}
    result = f.evaluate(notice)
    assert result["pass"] is False
    assert result["reason"] == "country"


def test_ingest_filter_allow_all_bypasses_country_check():
    f = IngestFilter()
    notice = {"title": "Security guarding services", "category": "Security", "country": "France"}
    assert f.passes(notice, {"country_allowlist": "*"})


def test_ingest_filter_rejects_non_security_category():
    f = IngestFilter()
    notice = {"title": "Office stationery supply", "category": "Stationery", "country": "UAE"}
    result = f.evaluate(notice)
    assert result["pass"] is False
    assert result["reason"] == "security_category"


# --- TED country resolver ---
def test_ted_country_resolver_alpha3_to_name():
    resolver = TedCountryResolver()
    assert resolver.resolve_from_codes(["ARE"]) == "United Arab Emirates"
    assert resolver.resolve_from_codes(["XX9"]) == ""


# --- connectors (mocked HTTP, no real network) ---
def test_ted_connector_normalizes_and_filters_notices():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "totalNoticeCount": 1,
            "notices": [{
                "publication-number": "123456-2026",
                "notice-title": {"eng": "Static security guarding services"},
                "buyer-name": {"eng": "Ministry of Interior"},
                "place-of-performance": ["ARE"],
                "estimated-value-proc": "500000",
                "estimated-value-cur-proc": "USD",
                "publication-date": "2026-07-01",
                "deadline-receipt-tender-date-lot": "2026-09-01",
                "links": {"html": {"ENG": "https://ted.europa.eu/en/notice/-/detail/123456-2026"}},
            }],
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = TedNoticeConnector(client=client)
    result = connector.search({"query": "security"})
    assert result["skipped"] == 0
    assert len(result["notices"]) == 1
    notice = result["notices"][0]
    assert notice["external_id"] == "123456-2026"
    assert notice["country"] == "United Arab Emirates"
    assert notice["estimated_value"] == 500000.0
    assert notice["currency"] == "USD"


def test_ted_connector_skips_notices_that_fail_the_ingest_filter():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "totalNoticeCount": 1,
            "notices": [{
                "publication-number": "999-2026",
                "notice-title": {"eng": "Office stationery supply"},
                "place-of-performance": ["FRA"],
            }],
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = TedNoticeConnector(client=client)
    result = connector.search({})
    assert result["notices"] == []
    assert result["skipped"] == 1


def test_ted_connector_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = TedNoticeConnector(client=client)
    with pytest.raises(RuntimeError):
        connector.search({})


UNGM_ROW_HTML = """
<div class="dataRow" data-noticeid="98765">
  <div class="resultTitle"><span class="ungm-title">
    <a href="/Public/Notice/98765">Static security guarding services</a></span></div>
  <div class="resultAgency">UNDP</div>
  <div class="deadline"><span>15-Sep-2026 23:59</span></div>
  <div class="tableCell">col1</div>
  <div class="tableCell">col2</div>
  <div class="tableCell">01-Jul-2026</div>
  <div class="tableCell">col4</div>
  <div class="tableCell">Request for Proposal</div>
  <div class="tableCell">col6</div>
  <div class="tableCell">Kenya</div>
</div>
"""


def test_ungm_connector_parses_notice_rows():
    connector = UngmNoticeConnector()
    notices = connector.parse_notice_rows(UNGM_ROW_HTML)
    assert len(notices) == 1
    assert notices[0]["external_id"] == "98765"
    assert notices[0]["buyer"] == "UNDP"
    assert notices[0]["country"] == "Kenya"
    assert notices[0]["title"] == "Static security guarding services"


def test_ungm_connector_search_enriches_and_filters(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=UNGM_ROW_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = UngmNoticeConnector(client=client)
    monkeypatch.setattr(connector, "fetch_detail", lambda notice_id: {})
    result = connector.search({})
    assert len(result["notices"]) == 1
    assert result["skipped"] == 0


# --- opportunity service (scan orchestration + mutation) ---
async def test_scan_requires_source_to_be_active_first():
    svc = OpportunityService()
    with pytest.raises(SourceInactiveError):
        await svc.scan_ted("acme", "agent-1", {})


async def test_scan_ted_ingests_and_qualifies_opportunities(monkeypatch):
    svc = OpportunityService()
    await svc.update_source_status("acme", "agent-1", "ted", "active")

    def fake_search(filters=None):
        return {
            "payload": {}, "total_notice_count": 1, "skipped": 0,
            "notices": [{
                "external_id": "T-1", "title": "Static security guarding services", "buyer": "MoI",
                "country": "United Arab Emirates", "category": "Security services",
                "source_url": "https://ted.europa.eu/x", "estimated_value": 100000.0, "currency": "USD",
                "published_at": None, "deadline_at": datetime.now(timezone.utc) + timedelta(days=40),
                "raw": {},
            }],
        }

    monkeypatch.setattr(svc.ted, "search", fake_search)
    result = await svc.scan_ted("acme", "agent-1", {})
    assert result["created"] == 1
    opp = result["opportunities"][0]
    assert opp.recommendation == "Bid"
    assert opp.stage == "qualified"

    summary = await svc.dashboard_summary("acme", "agent-1")
    assert summary["total"] == 1
    assert summary["qualified"] == 1


async def test_next_scan_at_set_after_scan(monkeypatch):
    svc = OpportunityService(scan_interval_minutes=5)
    await svc.update_source_status("acme", "agent-1", "ted", "active")

    def fake_search(filters=None):
        return {"payload": {}, "total_notice_count": 0, "skipped": 0, "notices": []}

    monkeypatch.setattr(svc.ted, "search", fake_search)
    source = (await svc.scan_ted("acme", "agent-1", {}))["source"]
    assert source.last_scan_at is not None
    # next scan is one interval after the last scan (matches the scheduler's due-ness rule)
    nxt = source.next_scan_at(scan_interval_minutes=5)
    assert nxt is not None and nxt == source.last_scan_at + timedelta(minutes=5)


async def test_scan_does_not_revive_archived_opportunity(monkeypatch):
    svc = OpportunityService()
    mutation = OpportunityMutationService(opportunities=svc.opportunities, activity_logs=svc.activity_logs)
    await svc.update_source_status("acme", "agent-1", "ted", "active")

    def fake_search(filters=None):
        return {"payload": {}, "skipped": 0, "notices": [{
            "external_id": "T-2", "title": "Static security guarding services", "buyer": "MoI",
            "country": "UAE", "estimated_value": 1.0, "currency": "USD", "category": "Security",
            "source_url": "u", "published_at": None, "deadline_at": None, "raw": {},
        }]}

    monkeypatch.setattr(svc.ted, "search", fake_search)
    first = await svc.scan_ted("acme", "agent-1", {})
    opp = first["opportunities"][0]
    await mutation.archive(opp, actor_user_id="u1")

    second = await svc.scan_ted("acme", "agent-1", {})
    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["opportunities"] == []


async def test_manual_create_and_update_fields():
    mutation = OpportunityMutationService()
    opp = await mutation.create_manual("acme", "agent-1", {
        "title": "Manual security tender", "country": "Kenya", "buyer": "Buyer Co", "estimated_value": 1000,
    }, actor_user_id="u1")
    assert opp.source_key == "manual"
    assert opp.stage == "awaiting_review"

    updated = await mutation.update_fields(opp, {"title": "Updated title"}, actor_user_id="u1")
    assert updated.title == "Updated title"
    assert updated.updated_by == "u1"


async def test_archive_and_restore_roundtrip():
    mutation = OpportunityMutationService()
    opp = await mutation.create_manual("acme", "agent-1", {"title": "X"}, run_qualification=False)
    archived = await mutation.archive(opp)
    assert archived.is_archived()
    restored = await mutation.restore(archived)
    assert not restored.is_archived()


# --- Salesforce (mocked HTTP, no real network -- proves the authorization_code+PKCE+refresh
# flow, NOT client_credentials) ---
def test_salesforce_authorize_url_uses_authorization_code_grant_with_pkce():
    auth = SalesforceAuthService()
    from app.core.config import get_settings

    get_settings.cache_clear()
    import os

    os.environ["SALESFORCE_CLIENT_ID"] = "cid"
    os.environ["SALESFORCE_CLIENT_SECRET"] = "secret"
    try:
        result = auth.build_authorize_url("acme", "agent-1")
        assert "response_type=code" in result["authorizeUrl"]
        assert "code_challenge=" in result["authorizeUrl"]
        assert "code_challenge_method=S256" in result["authorizeUrl"]
        assert result["state"] in auth._state_cache
    finally:
        del os.environ["SALESFORCE_CLIENT_ID"]
        del os.environ["SALESFORCE_CLIENT_SECRET"]
        get_settings.cache_clear()


def test_salesforce_push_requires_validated_stage():
    from app.modules.sales_intelligence.models import Opportunity

    auth = SalesforceAuthService()
    push = SalesforcePushService(auth=auth)
    opp = Opportunity(id="o1", tenant="acme", agent_id="agent-1", external_id="e1", source_key="ted",
                      source_name="TED", stage="ingested")
    import asyncio

    with pytest.raises(SalesforceError):
        asyncio.run(push.push(opp))


async def test_salesforce_push_creates_opportunity_via_authorization_code_token():
    from app.modules.sales_intelligence.models import Opportunity, SalesforceConnection

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer at-1"
        return httpx.Response(201, json={"id": "006xx0000001"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    auth = SalesforceAuthService()
    conn = SalesforceConnection(tenant="acme", agent_id="agent-1", status="connected",
                                instance_url="https://acme.my.salesforce.com",
                                access_token="unused")
    from app.core.crypto import encrypt

    conn.access_token = encrypt("at-1")
    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await auth.connections.update(conn)

    push = SalesforcePushService(auth=auth, client=client)
    opp = Opportunity(id="o1", tenant="acme", agent_id="agent-1", external_id="e1", source_key="ted",
                      source_name="TED", title="Tender", stage="validated")
    pushed = await push.push(opp)
    assert pushed.salesforce_opportunity_id == "006xx0000001"
    assert pushed.stage == "pushed"


class _CopyingOpportunityStore:
    """Mimics the Postgres store's round-trip semantics: get() returns a *fresh* object each call
    (not the shared reference the in-memory store hands back), so it catches a push service that
    mutates the opportunity but never persists it."""

    def __init__(self) -> None:
        self._by_id: dict = {}

    async def add(self, opp):
        import dataclasses

        self._by_id[opp.id] = dataclasses.replace(opp)
        return opp

    async def update(self, opp):
        import dataclasses

        self._by_id[opp.id] = dataclasses.replace(opp)
        return opp

    async def get(self, tenant, agent_id, opp_id):
        import dataclasses

        row = self._by_id.get(opp_id)
        return dataclasses.replace(row) if row else None


async def test_salesforce_push_persists_stage_to_the_store():
    """Regression: push must persist the mutated stage/salesforce_* columns, not just return the
    in-memory object -- otherwise the result is silently lost under the Postgres store."""
    from app.core.crypto import encrypt
    from app.modules.sales_intelligence.models import Opportunity, SalesforceConnection

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "006xx0000099"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    auth = SalesforceAuthService()
    conn = SalesforceConnection(tenant="acme", agent_id="agent-1", status="connected",
                                instance_url="https://acme.my.salesforce.com", access_token="unused")
    conn.access_token = encrypt("at-1")
    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await auth.connections.update(conn)

    store = _CopyingOpportunityStore()
    opp = Opportunity(id="o1", tenant="acme", agent_id="agent-1", external_id="e1", source_key="ted",
                      source_name="TED", title="Tender", stage="validated")
    await store.add(opp)

    push = SalesforcePushService(auth=auth, client=client, opportunities=store)
    await push.push(opp)

    reloaded = await store.get("acme", "agent-1", "o1")
    assert reloaded.stage == "pushed"
    assert reloaded.salesforce_opportunity_id == "006xx0000099"
    assert reloaded.salesforce_push_status == "success"


# --- router (API-level) ---
def test_sales_intelligence_sources_round_trip_via_api(client):
    cookies = auth_cookies(tenant="acme")
    resp = client.get("/api/v1/sales-intelligence/agent-si-1/sources", cookies=cookies)
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    assert {s["sourceKey"] for s in sources} == {"ungm", "ted"}

    # a disabled source has no scheduled next scan; enabling one populates it (so the FE stops
    # showing "Next scan --")
    assert all(s["nextScanAt"] is None for s in sources)

    patch = client.patch("/api/v1/sales-intelligence/agent-si-1/sources/ted", cookies=cookies,
                         json={"status": "active"})
    assert patch.status_code == 200
    assert patch.json()["source"]["status"] == "active"
    assert patch.json()["source"]["nextScanAt"] is not None


def test_sales_intelligence_manual_create_and_review_via_api(client):
    cookies = auth_cookies(tenant="acme")
    created = client.post("/api/v1/sales-intelligence/agent-si-2/opportunities", cookies=cookies, json={
        "title": "Static security guarding services", "country": "Kenya", "buyer": "UN Agency",
        "estimated_value": 20000,
    })
    assert created.status_code == 201
    opp = created.json()["opportunity"]
    opp_id = opp["id"]

    detail = client.get(f"/api/v1/sales-intelligence/agent-si-2/opportunities/{opp_id}", cookies=cookies)
    assert detail.status_code == 200
    assert "detail" in detail.json()["opportunity"]

    review = client.post(f"/api/v1/sales-intelligence/agent-si-2/opportunities/{opp_id}/review", cookies=cookies,
                         json={"decision": "approved", "notes": "Looks good"})
    assert review.status_code == 200
    assert review.json()["opportunity"]["stage"] == "validated"

    history = client.get(f"/api/v1/sales-intelligence/agent-si-2/opportunities/{opp_id}/history", cookies=cookies)
    assert history.status_code == 200
    assert len(history.json()["history"]) >= 1


def test_sales_intelligence_activity_logs_response_shape(client):
    """The FE (creator/lib/api.ts getSalesActivityLogs) reads `.logs`/`.total`; the endpoint must
    return that shape (regression for the old `activityLogs` key that left the log table empty)."""
    cookies = auth_cookies(tenant="acme")
    client.post("/api/v1/sales-intelligence/agent-si-logs/opportunities", cookies=cookies,
                json={"title": "Logged opportunity"})
    resp = client.get("/api/v1/sales-intelligence/agent-si-logs/activity-logs", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["logs"], list) and len(body["logs"]) >= 1
    assert body["total"] == len(body["logs"])


def test_sales_intelligence_requires_editor_role_for_mutations(client):
    viewer_cookies = auth_cookies(tenant="acme", role="viewer")
    resp = client.post("/api/v1/sales-intelligence/agent-si-3/opportunities", cookies=viewer_cookies,
                       json={"title": "X"})
    assert resp.status_code == 403


def test_sales_intelligence_pipeline_is_tenant_isolated(client):
    cookies_a = auth_cookies(tenant="acme")
    cookies_b = auth_cookies(tenant="beta")
    client.post("/api/v1/sales-intelligence/agent-si-4/opportunities", cookies=cookies_a, json={"title": "X"})
    other = client.get("/api/v1/sales-intelligence/agent-si-4/opportunities", cookies=cookies_b)
    assert other.json()["opportunities"] == []


def test_sales_intelligence_salesforce_status_reports_not_configured(client):
    cookies = auth_cookies(tenant="acme")
    resp = client.get("/api/v1/sales-intelligence/agent-si-5/salesforce/status", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()["salesforce"]
    assert body["connected"] is False
    assert body["configured"] is False
