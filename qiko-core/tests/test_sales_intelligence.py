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


# --- config-driven qualification (per-agent si_* config) ---
_CATERING_OPP = {
    "title": "Provision of school catering and canteen services", "category": "Catering",
    "country": "Portugal", "buyer": "Ministry of Education", "estimated_value": 250000,
}


def _with_deadline(opp: dict) -> dict:
    return {**opp, "deadline_at": datetime.now(timezone.utc) + timedelta(days=45)}


def test_with_config_empty_or_missing_matches_idg_defaults():
    base = QualificationService()
    opp = _with_deadline({
        "title": "Provision of static security guarding services", "category": "Security services",
        "country": "United Arab Emirates", "buyer": "Ministry of Interior", "estimated_value": 500000,
    })
    assert base.with_config(None).qualify(opp) == base.qualify(opp)
    assert base.with_config({}).qualify(opp) == base.qualify(opp)


def test_default_keywords_still_no_bid_a_non_security_opportunity():
    result = QualificationService().qualify(_with_deadline(_CATERING_OPP))
    assert result["recommendation"] == "No Bid"
    assert result["stage"] == "rejected"


def test_custom_keywords_and_countries_change_score_and_recommendation():
    scorer = QualificationService().with_config({
        "si_service_keywords": ["catering", "canteen", "food", "kitchen"],
        "si_target_countries": ["Portugal", "Spain"],
    })
    result = scorer.qualify(_with_deadline(_CATERING_OPP))
    assert result["recommendation"] != "No Bid"
    assert result["stage"] != "rejected"
    assert result["qualification_dimensions"]["serviceMatch"] > 0
    assert result["qualification_dimensions"]["geography"] == 100


def test_custom_config_no_bids_an_out_of_scope_security_opportunity():
    # An agent configured for catering should not bid on a pure security tender.
    scorer = QualificationService().with_config({"si_service_keywords": ["catering", "canteen"]})
    result = scorer.qualify(_with_deadline({
        "title": "Static security guarding services", "category": "Security",
        "country": "United Arab Emirates", "buyer": "MoI", "estimated_value": 500000,
    }))
    assert result["recommendation"] == "No Bid"


def test_invalid_or_empty_config_values_fall_back_to_defaults():
    base = QualificationService()
    opp = _with_deadline({"title": "Security guarding services", "category": "Security",
                          "country": "Kenya", "buyer": "Buyer", "estimated_value": 1000})
    for bad in ({"si_service_keywords": []}, {"si_service_keywords": "security"},
                {"si_service_keywords": [1, 2]}, {"si_target_countries": []},
                {"si_target_countries": "Portugal"}):
        assert base.with_config(bad).qualify(opp) == base.qualify(opp)


def test_target_countries_from_config_accepts_names_and_dicts():
    from_names = TargetCountries.from_config(["Portugal", "Spain"])
    assert from_names.matches("Portugal") is True
    assert from_names.matches("United Arab Emirates") is False
    from_dicts = TargetCountries.from_config([{"code": "PT", "name": "Portugal", "aliases": ["portugal"]}])
    assert from_dicts.matches("portugal") is True
    # Empty / non-list falls back to the IDG default allowlist.
    assert TargetCountries.from_config([]).matches("United Arab Emirates") is True
    assert TargetCountries.from_config(None).matches("Kenya") is True


class _StubAgent:
    def __init__(self, config: dict) -> None:
        self.config = config


class _StubAgents:
    """Minimal AgentService-shaped resolver for exercising the per-agent scan path."""
    def __init__(self, config: dict) -> None:
        self._config = config

    async def get(self, tenant: str, agent_id: str):
        return _StubAgent(self._config)


async def test_scan_uses_per_agent_config_from_agents_resolver(monkeypatch):
    agents = _StubAgents({"si_service_keywords": ["catering", "canteen"],
                          "si_target_countries": ["Portugal"]})
    svc = OpportunityService(agents=agents)
    await svc.update_source_status("acme", "agent-1", "ted", "active")

    def fake_search(filters=None):
        return {"notices": [_with_deadline({**_CATERING_OPP, "external_id": "t1"})], "skipped": 0}

    monkeypatch.setattr(svc.ted, "search", fake_search)
    opp = (await svc.scan_ted("acme", "agent-1", {}))["opportunities"][0]
    assert opp.recommendation != "No Bid"


async def test_scan_without_agents_falls_back_to_idg_defaults(monkeypatch):
    svc = OpportunityService()  # no agents resolver, no explicit config
    await svc.update_source_status("acme", "agent-1", "ted", "active")

    def fake_search(filters=None):
        return {"notices": [_with_deadline({**_CATERING_OPP, "external_id": "t1"})], "skipped": 0}

    monkeypatch.setattr(svc.ted, "search", fake_search)
    opp = (await svc.scan_ted("acme", "agent-1", {}))["opportunities"][0]
    assert opp.recommendation == "No Bid"


async def test_create_manual_respects_explicit_agent_config():
    mutation = OpportunityMutationService()
    opp = await mutation.create_manual(
        "acme", "agent-1", dict(_CATERING_OPP), run_qualification=True,
        agent_config={"si_service_keywords": ["catering", "canteen"], "si_target_countries": ["Portugal"]})
    assert opp.recommendation != "No Bid"


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


def test_sales_intelligence_update_source_persists_scan_cadence(client):
    """FEATURE 1: per-source scan cadence is settable via PATCH, persisted, and validated; a
    'manual' cadence clears the scheduled next scan even while the source is active."""
    cookies = auth_cookies(tenant="acme")
    agent = "agent-si-cadence"
    client.get(f"/api/v1/sales-intelligence/{agent}/sources", cookies=cookies)

    # status + cadence in one patch
    patch = client.patch(f"/api/v1/sales-intelligence/{agent}/sources/ted", cookies=cookies,
                         json={"status": "active", "scan_cadence": "hourly"})
    assert patch.status_code == 200
    assert patch.json()["source"]["scanCadence"] == "hourly"
    assert patch.json()["source"]["nextScanAt"] is not None

    # persisted across a re-fetch
    sources = client.get(f"/api/v1/sales-intelligence/{agent}/sources", cookies=cookies).json()["sources"]
    ted = next(s for s in sources if s["sourceKey"] == "ted")
    assert ted["scanCadence"] == "hourly"

    # cadence-only patch works, and 'manual' means no scheduled next scan
    manual = client.patch(f"/api/v1/sales-intelligence/{agent}/sources/ted", cookies=cookies,
                          json={"scan_cadence": "manual"})
    assert manual.status_code == 200
    assert manual.json()["source"]["scanCadence"] == "manual"
    assert manual.json()["source"]["status"] == "active"
    assert manual.json()["source"]["nextScanAt"] is None

    # invalid cadence rejected; empty body rejected
    assert client.patch(f"/api/v1/sales-intelligence/{agent}/sources/ted", cookies=cookies,
                        json={"scan_cadence": "hyperspeed"}).status_code == 422
    assert client.patch(f"/api/v1/sales-intelligence/{agent}/sources/ted", cookies=cookies,
                        json={}).status_code == 422


def test_sales_intelligence_update_source_cadence_requires_editor_role(client):
    viewer_cookies = auth_cookies(tenant="acme", role="viewer")
    resp = client.patch("/api/v1/sales-intelligence/agent-si-cadence-rbac/sources/ted",
                        cookies=viewer_cookies, json={"scan_cadence": "daily"})
    assert resp.status_code == 403


def test_sales_intelligence_decision_history_aggregates_across_opportunities(client):
    """FEATURE 2: the agent-level decision history aggregates human-review decisions across all
    opportunities, honours the decision + reviewer filters, and reports correct summary counts."""
    cookies_a = auth_cookies(tenant="acme", user_id="rev-a")
    cookies_b = auth_cookies(tenant="acme", user_id="rev-b")
    agent = "agent-si-decisions"

    ids = []
    for i in range(3):
        r = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=cookies_a,
                        json={"title": f"Opportunity {i}", "run_qualification": False})
        ids.append(r.json()["opportunity"]["id"])

    # rev-a approves opp0 and rejects opp1; rev-b overrides (needs_review) opp2
    client.post(f"/api/v1/sales-intelligence/{agent}/opportunities/{ids[0]}/review", cookies=cookies_a,
                json={"decision": "approved"})
    client.post(f"/api/v1/sales-intelligence/{agent}/opportunities/{ids[1]}/review", cookies=cookies_a,
                json={"decision": "rejected"})
    client.post(f"/api/v1/sales-intelligence/{agent}/opportunities/{ids[2]}/review", cookies=cookies_b,
                json={"decision": "needs_review"})

    body = client.get(f"/api/v1/sales-intelligence/{agent}/decision-history", cookies=cookies_a).json()
    assert body["summary"] == {"approved": 1, "rejected": 1, "overrides": 1, "total": 3}
    assert len(body["decisionHistory"]) == 3
    assert all("opportunityTitle" in e and "opportunityStage" in e for e in body["decisionHistory"])
    assert {r["id"] for r in body["reviewers"]} == {"rev-a", "rev-b"}

    # decision filter: 'override' maps to the stored needs_review decision
    overrides = client.get(f"/api/v1/sales-intelligence/{agent}/decision-history?decision=override",
                           cookies=cookies_a).json()
    assert overrides["summary"] == {"approved": 0, "rejected": 0, "overrides": 1, "total": 1}
    assert overrides["decisionHistory"][0]["decision"] == "needs_review"

    # reviewer filter narrows the rows but keeps the full reviewers dropdown
    by_a = client.get(f"/api/v1/sales-intelligence/{agent}/decision-history?reviewer_user_id=rev-a",
                      cookies=cookies_a).json()
    assert by_a["summary"]["total"] == 2
    assert {e["reviewerUserId"] for e in by_a["decisionHistory"]} == {"rev-a"}
    assert {r["id"] for r in by_a["reviewers"]} == {"rev-a", "rev-b"}

    # invalid decision rejected; viewer can read (parity with the other read endpoints)
    assert client.get(f"/api/v1/sales-intelligence/{agent}/decision-history?decision=maybe",
                      cookies=cookies_a).status_code == 422
    assert client.get(f"/api/v1/sales-intelligence/{agent}/decision-history",
                      cookies=auth_cookies(tenant="acme", role="viewer")).status_code == 200


def test_sales_intelligence_decision_history_is_tenant_isolated(client):
    agent = "agent-si-dh-iso"
    cookies_a = auth_cookies(tenant="acme")
    created = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=cookies_a,
                          json={"title": "Tenant A opp", "run_qualification": False})
    opp_id = created.json()["opportunity"]["id"]
    client.post(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}/review", cookies=cookies_a,
                json={"decision": "approved"})

    other = client.get(f"/api/v1/sales-intelligence/{agent}/decision-history",
                       cookies=auth_cookies(tenant="beta")).json()
    assert other["decisionHistory"] == []
    assert other["summary"] == {"approved": 0, "rejected": 0, "overrides": 0, "total": 0}


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


def test_sales_intelligence_review_accepts_canonical_decisions(client):
    """Regression for the approve/reject 422 bug: the endpoint accepts the canonical
    approved/rejected values and rejects the old non-canonical approve/reject aliases."""
    cookies = auth_cookies(tenant="acme")
    created = client.post("/api/v1/sales-intelligence/agent-si-review/opportunities", cookies=cookies,
                          json={"title": "Static security guarding services", "country": "Kenya", "buyer": "UN"})
    opp_id = created.json()["opportunity"]["id"]

    rejected = client.post(f"/api/v1/sales-intelligence/agent-si-review/opportunities/{opp_id}/review",
                           cookies=cookies, json={"decision": "rejected", "notes": "Out of scope"})
    assert rejected.status_code == 200
    assert rejected.json()["opportunity"]["stage"] == "rejected"

    approved = client.post(f"/api/v1/sales-intelligence/agent-si-review/opportunities/{opp_id}/review",
                           cookies=cookies, json={"decision": "approved"})
    assert approved.status_code == 200
    assert approved.json()["opportunity"]["stage"] == "validated"

    # The non-canonical alias the FE used to send is still refused (422, never accepted).
    legacy = client.post(f"/api/v1/sales-intelligence/agent-si-review/opportunities/{opp_id}/review",
                         cookies=cookies, json={"decision": "approve"})
    assert legacy.status_code == 422


def test_sales_intelligence_stage_transition_via_api(client):
    cookies = auth_cookies(tenant="acme")
    created = client.post("/api/v1/sales-intelligence/agent-si-trans/opportunities", cookies=cookies,
                          json={"title": "Move me", "run_qualification": False})
    opp_id = created.json()["opportunity"]["id"]

    moved = client.post(f"/api/v1/sales-intelligence/agent-si-trans/opportunities/{opp_id}/transition",
                        cookies=cookies, json={"stage": "qualifying"})
    assert moved.status_code == 200
    assert moved.json()["opportunity"]["stage"] == "qualifying"

    # Salesforce-driven stages are not manually settable (must go through push-to-salesforce).
    pushed = client.post(f"/api/v1/sales-intelligence/agent-si-trans/opportunities/{opp_id}/transition",
                         cookies=cookies, json={"stage": "pushed"})
    assert pushed.status_code == 422

    # Unknown stage is rejected too.
    bogus = client.post(f"/api/v1/sales-intelligence/agent-si-trans/opportunities/{opp_id}/transition",
                        cookies=cookies, json={"stage": "not_a_stage"})
    assert bogus.status_code == 422


def test_sales_intelligence_activity_logs_actions_or_filter(client):
    cookies = auth_cookies(tenant="acme")
    agent = "agent-si-actions"
    created = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=cookies,
                          json={"title": "Filter me", "run_qualification": False})
    opp_id = created.json()["opportunity"]["id"]
    client.post(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}/transition",
                cookies=cookies, json={"stage": "qualifying"})

    all_actions = {log["action"] for log in
                   client.get(f"/api/v1/sales-intelligence/{agent}/activity-logs", cookies=cookies).json()["logs"]}
    assert {"opportunity_created_manual", "opportunity_stage_changed"} <= all_actions

    # Single-value OR filter.
    single = client.get(f"/api/v1/sales-intelligence/{agent}/activity-logs?actions=opportunity_stage_changed",
                        cookies=cookies).json()["logs"]
    assert single and all(log["action"] == "opportunity_stage_changed" for log in single)

    # Repeated params act as an OR set.
    both = client.get(f"/api/v1/sales-intelligence/{agent}/activity-logs"
                      "?actions=opportunity_stage_changed&actions=opportunity_created_manual",
                      cookies=cookies).json()["logs"]
    assert {log["action"] for log in both} == {"opportunity_stage_changed", "opportunity_created_manual"}


def test_sales_intelligence_opportunities_limit_all_and_reviewer_filter(client):
    cookies = auth_cookies(tenant="acme")
    agent = "agent-si-limit"
    for i in range(3):
        client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=cookies,
                    json={"title": f"Opportunity {i}", "run_qualification": False})

    listed = client.get(f"/api/v1/sales-intelligence/{agent}/opportunities?limit=all",
                        cookies=cookies).json()["opportunities"]
    assert len(listed) == 3

    target_id = listed[0]["id"]
    client.patch(f"/api/v1/sales-intelligence/{agent}/opportunities/{target_id}/assign-reviewer",
                 cookies=cookies, json={"user_id": "rev-1", "name": "Reviewer One"})

    filtered = client.get(f"/api/v1/sales-intelligence/{agent}/opportunities"
                          "?limit=all&assigned_reviewer_user_id=rev-1", cookies=cookies).json()["opportunities"]
    assert len(filtered) == 1
    assert filtered[0]["assignedReviewerUserId"] == "rev-1"


def test_sales_intelligence_salesforce_status_reports_not_configured(client):
    cookies = auth_cookies(tenant="acme")
    resp = client.get("/api/v1/sales-intelligence/agent-si-5/salesforce/status", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()["salesforce"]
    assert body["connected"] is False
    assert body["configured"] is False


# --- Manual "add an opportunity" flow (enriched create/edit/delete/archive) ---

_ENRICHED_CREATE_BODY = {
    "title": "Static security guarding services",
    "buyer": "UN Agency",
    "country": "Kenya",
    "category": "Security services",
    "estimated_value": 250000,
    "currency": "USD",
    "deadline_at": "2099-01-31",
    "source_url": "https://example.test/notice/42",
    "reference": "REF-42",
    "notice_type": "Request for Proposal",
    "security_clearance": "SC",
    "framework": "G-Cloud",
    "contract_duration": "24 months",
    "technology": "CCTV",
    "extraction_confidence": 88,
    "contacts": [{"name": "Jane Doe", "email": "jane@example.test", "phone": "+254700000000"}],
    "links": [{"url": "https://example.test/tender", "description": "Tender portal"}],
    "executive_summary": "High-value static guarding tender in a target market.",
    "risk_summary": "Tight mobilisation window.",
    "opportunity_summary": "Strong fit for IDG security services.",
    "requirements": ["ISO 18788", "Local licensing"],
    "deliverables": ["Guarding roster", "Control room"],
    "qualification_score": 82,
    "recommendation": "Bid",
    "confidence": 90,
    "ai_reasoning": "Manually assessed as a strong fit.",
    "recommendations": ["Engage local partner", "Confirm licensing"],
    "notes": "Flagged by BD team.",
    "run_qualification": False,
}


def test_sales_intelligence_manual_create_persists_enriched_fields(client):
    """The manual create flow captures Ali's richer field set and surfaces it back through the
    opportunity detail tabs (overview / summary / qualification / notes)."""
    cookies = auth_cookies(tenant="acme")
    agent = "agent-si-enriched"
    created = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=cookies,
                          json=_ENRICHED_CREATE_BODY)
    assert created.status_code == 201
    opp = created.json()["opportunity"]
    opp_id = opp["id"]
    assert opp["isManual"] is True
    assert opp["stage"] == "awaiting_review"
    # Column fields set from the payload (qualification skipped, so manual values stick).
    assert opp["recommendation"] == "Bid"
    assert opp["qualificationScore"] == 82
    assert opp["confidence"] == 90

    detail = client.get(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}", cookies=cookies).json()
    d = detail["opportunity"]["detail"]
    assert d["overview"]["reference"] == "REF-42"
    assert d["overview"]["noticeType"] == "Request for Proposal"
    assert d["overview"]["securityClearance"] == "SC"
    assert d["overview"]["framework"] == "G-Cloud"
    assert d["overview"]["contractDuration"] == "24 months"
    assert d["overview"]["technology"] == "CCTV"
    assert d["overview"]["extractionConfidence"] == 88
    assert d["overview"]["contacts"][0]["email"] == "jane@example.test"
    assert d["overview"]["links"][0]["url"] == "https://example.test/tender"
    assert d["summary"]["executiveSummary"] == "High-value static guarding tender in a target market."
    assert d["summary"]["riskSummary"] == "Tight mobilisation window."
    assert d["summary"]["requirements"] == ["ISO 18788", "Local licensing"]
    assert d["summary"]["deliverables"] == ["Guarding roster", "Control room"]
    assert d["qualification"]["aiReasoning"] == "Manually assessed as a strong fit."
    assert d["qualification"]["recommendations"] == ["Engage local partner", "Confirm licensing"]
    assert d["notes"]["humanReviewNotes"] == "Flagged by BD team."


def test_sales_intelligence_manual_update_edits_enriched_fields(client):
    cookies = auth_cookies(tenant="acme")
    agent = "agent-si-enriched-edit"
    created = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=cookies,
                          json=_ENRICHED_CREATE_BODY)
    opp_id = created.json()["opportunity"]["id"]

    patched = client.patch(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}", cookies=cookies, json={
        "title": "Static security guarding services (revised)",
        "reference": "REF-99",
        "requirements": ["ISO 18788"],
        "recommendation": "Review",
        "notes": "Updated after review.",
    })
    assert patched.status_code == 200
    assert patched.json()["opportunity"]["title"].endswith("(revised)")
    assert patched.json()["opportunity"]["recommendation"] == "Review"

    d = client.get(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}",
                   cookies=cookies).json()["opportunity"]["detail"]
    assert d["overview"]["reference"] == "REF-99"
    assert d["summary"]["requirements"] == ["ISO 18788"]
    assert d["notes"]["humanReviewNotes"] == "Updated after review."
    # Untouched enriched fields survive the partial patch.
    assert d["overview"]["noticeType"] == "Request for Proposal"


def test_sales_intelligence_manual_delete_removes_opportunity(client):
    cookies = auth_cookies(tenant="acme")
    agent = "agent-si-delete"
    created = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=cookies,
                          json={"title": "Delete me", "run_qualification": False})
    opp_id = created.json()["opportunity"]["id"]

    deleted = client.delete(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}", cookies=cookies)
    assert deleted.status_code == 200

    assert client.get(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}",
                      cookies=cookies).status_code == 404
    listed = client.get(f"/api/v1/sales-intelligence/{agent}/opportunities?limit=all",
                        cookies=cookies).json()["opportunities"]
    assert all(o["id"] != opp_id for o in listed)


def test_sales_intelligence_manual_delete_requires_editor_role(client):
    agent = "agent-si-delete-rbac"
    owner_cookies = auth_cookies(tenant="acme")
    created = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=owner_cookies,
                          json={"title": "Guard me", "run_qualification": False})
    opp_id = created.json()["opportunity"]["id"]

    viewer = client.delete(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}",
                           cookies=auth_cookies(tenant="acme", role="viewer"))
    assert viewer.status_code == 403
    editor = client.delete(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}",
                           cookies=auth_cookies(tenant="acme", role="editor"))
    assert editor.status_code == 200


def test_sales_intelligence_archive_restore_roundtrip_via_api(client):
    cookies = auth_cookies(tenant="acme")
    agent = "agent-si-archive"
    created = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities", cookies=cookies,
                          json={"title": "Archive me", "run_qualification": False})
    opp_id = created.json()["opportunity"]["id"]

    archived = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}/archive", cookies=cookies)
    assert archived.status_code == 200
    assert archived.json()["opportunity"]["isArchived"] is True

    # Hidden from the default list, visible via archived_only.
    default_list = client.get(f"/api/v1/sales-intelligence/{agent}/opportunities?limit=all",
                              cookies=cookies).json()["opportunities"]
    assert all(o["id"] != opp_id for o in default_list)
    archived_list = client.get(f"/api/v1/sales-intelligence/{agent}/opportunities?limit=all&archived_only=true",
                               cookies=cookies).json()["opportunities"]
    assert any(o["id"] == opp_id for o in archived_list)

    restored = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}/restore", cookies=cookies)
    assert restored.status_code == 200
    assert restored.json()["opportunity"]["isArchived"] is False
    back = client.get(f"/api/v1/sales-intelligence/{agent}/opportunities?limit=all",
                      cookies=cookies).json()["opportunities"]
    assert any(o["id"] == opp_id for o in back)


def test_sales_intelligence_manual_mutations_are_tenant_scoped(client):
    """A tenant B user can neither edit, archive nor delete tenant A's opportunity (BOLA-safe 404)."""
    agent = "agent-si-tenant"
    created = client.post(f"/api/v1/sales-intelligence/{agent}/opportunities",
                          cookies=auth_cookies(tenant="acme"),
                          json={"title": "Tenant A only", "run_qualification": False})
    opp_id = created.json()["opportunity"]["id"]
    beta = auth_cookies(tenant="beta")

    assert client.patch(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}",
                        cookies=beta, json={"title": "hijack"}).status_code == 404
    assert client.post(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}/archive",
                       cookies=beta).status_code == 404
    assert client.delete(f"/api/v1/sales-intelligence/{agent}/opportunities/{opp_id}",
                        cookies=beta).status_code == 404


# --- R2: persisted ingest filters (per-agent) --------------------------------------------------

def test_ingest_filters_default_and_round_trip(client):
    cookies = auth_cookies(tenant="acme")
    agent = "agent-si-ingest-1"
    # Defaults for a fresh agent match deployed Staging (query on, keyword "security", allowlists bypassed).
    got = client.get(f"/api/v1/sales-intelligence/{agent}/ingest-filters", cookies=cookies)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["queryEnabled"] is True
    assert body["queryKeyword"] == "security"
    assert body["allCountries"] is True
    assert body["allCategories"] is True
    # Persist a change and read it back.
    patched = client.patch(f"/api/v1/sales-intelligence/{agent}/ingest-filters", cookies=cookies,
                           json={"query_enabled": False, "query_keyword": "guard services",
                                 "all_countries": False, "all_categories": False})
    assert patched.status_code == 200, patched.text
    p = patched.json()
    assert p["queryEnabled"] is False and p["queryKeyword"] == "guard services"
    assert p["allCountries"] is False and p["allCategories"] is False
    again = client.get(f"/api/v1/sales-intelligence/{agent}/ingest-filters", cookies=cookies).json()
    assert again["queryEnabled"] is False and again["queryKeyword"] == "guard services"
    assert again["allCountries"] is False and again["allCategories"] is False


def test_ingest_filters_patch_requires_editor_role(client):
    viewer = auth_cookies(tenant="acme", role="viewer")
    resp = client.patch("/api/v1/sales-intelligence/agent-si-ingest-rbac/ingest-filters",
                         cookies=viewer, json={"query_keyword": "x"})
    assert resp.status_code == 403, resp.text


def test_ingest_filters_are_tenant_scoped(client):
    agent = "agent-si-ingest-iso"
    client.patch(f"/api/v1/sales-intelligence/{agent}/ingest-filters", cookies=auth_cookies(tenant="acme"),
                 json={"query_keyword": "acme-only"})
    other = client.get(f"/api/v1/sales-intelligence/{agent}/ingest-filters",
                       cookies=auth_cookies(tenant="globex")).json()
    # A different tenant must not see acme's saved keyword (fresh default instead).
    assert other["queryKeyword"] == "security"


def test_merge_ingest_filter_fills_defaults_and_respects_explicit():
    from app.modules.sales_intelligence.models import IngestFilterSetting
    from app.modules.sales_intelligence.router import _merge_ingest_filter
    setting = IngestFilterSetting(tenant="acme", agent_id="a", query_enabled=True,
                                  query_keyword="security", all_countries=True, all_categories=True)
    # Empty request -> saved keyword + both allowlist bypasses applied.
    m = _merge_ingest_filter({}, setting)
    assert m == {"query": "security", "country_allowlist": "*", "category_allowlist": "*"}
    # Explicit request values win; disabled query + no bypass adds nothing.
    off = IngestFilterSetting(tenant="acme", agent_id="a", query_enabled=False, query_keyword="x",
                              all_countries=False, all_categories=False)
    m2 = _merge_ingest_filter({"query": "explicit", "country_allowlist": "RO"}, off)
    assert m2 == {"query": "explicit", "country_allowlist": "RO"}
