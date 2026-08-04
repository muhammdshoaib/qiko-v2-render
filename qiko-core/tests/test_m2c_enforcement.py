import asyncio
import threading

import pytest

from app.core.config import get_settings
from app.core.deps import WorkerUnavailable
from app.modules.agents.service import Agent, AgentService
from app.modules.ai.gateway import LLMResponse
from app.modules.crm.service import Contact
from app.modules.finance.service import FinanceService
from app.modules.sales_intelligence.salesforce import SalesforceAuthService
from app.modules.sales_intelligence.scheduler import scan_due_sources
from app.modules.sales_intelligence.service import OpportunityService
from app.core.crypto import encrypt
from tests.helpers import auth_cookies


def _seed_agent(client, tenant: str, agent_id: str, *, enabled: bool = True) -> None:
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=agent_id, tenant=tenant, name=agent_id, enabled=enabled)))


def test_disabled_worker_blocks_sales_finance_and_channel_mutations(client):
    tenant, agent_id = "m2c-disabled", "worker"
    _seed_agent(client, tenant, agent_id, enabled=False)
    cookies = auth_cookies(tenant, "owner")
    responses = [
        client.post(
            f"/api/v1/sales-intelligence/{agent_id}/scan/ungm",
            json={}, cookies=cookies,
        ),
        client.post(
            f"/api/v1/finance/{agent_id}/chat",
            json={"message": "Summarize"}, cookies=cookies,
        ),
        client.post(
            "/api/v1/channels/slack/link",
            json={"team_id": "T1", "slack_user_id": "U1", "worker_id": agent_id},
            cookies=cookies,
        ),
        client.post(
            "/api/v1/channels/sessions/external/worker",
            json={"worker": agent_id}, cookies=cookies,
        ),
    ]
    assert [response.status_code for response in responses] == [404] * len(responses)
    assert client.app.state.slack_links.resolve(tenant, "T1", "U1") is None
    assert client.app.state.channel_sessions.get(tenant, "external") is None


def test_disabled_worker_blocks_crm_contact_mutation(client):
    tenant, agent_id = "m2c-crm", "worker"
    _seed_agent(client, tenant, agent_id)
    contact = Contact(id="contact-1", tenant=tenant, agent_id=agent_id, name="Lead")
    asyncio.run(client.app.state.crm.contacts.add(contact))
    asyncio.run(client.app.state.agents.set_enabled(
        tenant, agent_id, False, changed_by_email="admin@invalid"))
    response = client.patch(
        "/api/v1/crm/contacts/contact-1", json={"name": "Changed"},
        cookies=auth_cookies(tenant, "owner"),
    )
    assert response.status_code == 404
    assert asyncio.run(client.app.state.crm.contacts.get(tenant, "contact-1")).name == "Lead"


async def test_finance_disable_during_provider_discards_exchange():
    agents = AgentService()
    await agents.store.add(Agent(id="finance", tenant="acme", name="Finance"))
    entered = threading.Event()
    release = threading.Event()

    class Provider:
        def generate(self, _prompt, **_kwargs):
            entered.set()
            release.wait(timeout=5)
            return LLMResponse(text="answer", model="test", stub=False)

    async def recheck() -> None:
        agent = await agents.get("acme", "finance")
        if agent is None or not agent.enabled:
            raise WorkerUnavailable

    service = FinanceService(provider=Provider())

    async def analytics(*_args, **_kwargs):
        return {"properties": [{"propertyRef": "P1"}], "summary": {}}

    service.analytics = analytics
    task = asyncio.create_task(service.chat(
        "acme", "finance", "question", recheck_worker=recheck))
    assert await asyncio.to_thread(entered.wait, 5)
    await agents.set_enabled("acme", "finance", False, changed_by_email="admin@invalid")
    release.set()
    with pytest.raises(WorkerUnavailable):
        await task
    assert (await service.history("acme", "finance"))["history"] == []


async def test_scheduler_requires_enabled_worker_and_does_not_scan_disabled():
    service = OpportunityService()
    source = await service.ensure_ungm_source("acme", "worker")
    source.status = "active"
    await service.sources.update(source)
    agents = AgentService()
    await agents.store.add(Agent(
        id="worker", tenant="acme", name="Worker", enabled=False))
    calls = 0

    async def scan(*_args, **_kwargs):
        nonlocal calls
        calls += 1

    service.scan_ungm = scan
    result = await scan_due_sources(service, agents=agents)
    assert result["failed"] == 1
    assert calls == 0


async def test_salesforce_oauth_rechecks_worker_before_token_exchange(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "salesforce_client_id", "client")
    monkeypatch.setattr(settings, "salesforce_client_secret", "secret")
    monkeypatch.setattr(settings, "salesforce_redirect_uri", "https://app.invalid/callback")
    auth = SalesforceAuthService()
    state = auth.build_authorize_url("acme", "disabled")["state"]
    exchanges = 0

    def exchange(*_args):
        nonlocal exchanges
        exchanges += 1
        return {}

    async def recheck(_tenant: str, _agent_id: str) -> None:
        raise WorkerUnavailable

    monkeypatch.setattr(auth, "_exchange_authorization_code", exchange)
    with pytest.raises(WorkerUnavailable):
        await auth.handle_callback("code", state, recheck_worker=recheck)
    assert exchanges == 0


async def test_channel_disable_during_external_call_returns_404(client, monkeypatch):
    tenant, agent_id = "m2c-channel-race", "worker"
    await client.app.state.agents.store.add(
        Agent(id=agent_id, tenant=tenant, name=agent_id))
    entered = threading.Event()
    release = threading.Event()

    class Gmail:
        def __init__(self, address="", app_password="", **_kw):
            pass

        def send(self, *_args):
            entered.set()
            release.wait(timeout=5)
            return {"sent": True}

    # Gmail is now a per-worker connection: store a credential and patch the client class.
    await client.app.state.agents.update_config(tenant, agent_id, {
        "gmail_address": "sender@invalid",
        "gmail_app_password_encrypted": encrypt("app-password"),
        "gmail_credentials_added": True,
    })
    monkeypatch.setattr("app.integrations.clients.GmailSmtpClient", Gmail)
    request = asyncio.create_task(asyncio.to_thread(
        client.post, "/api/v1/channels/gmail/send",
        json={
            "to": "recipient@invalid", "subject": "Subject",
            "body": "Body", "worker_id": agent_id,
        },
        cookies=auth_cookies(tenant, "owner"),
    ))
    assert await asyncio.to_thread(entered.wait, 5)
    await client.app.state.agents.set_enabled(
        tenant, agent_id, False, changed_by_email="admin@invalid")
    release.set()
    response = await request
    assert response.status_code == 404


async def test_slack_oauth_state_is_one_time_and_worker_checked(monkeypatch):
    import httpx
    from app.modules.channels.slack_oauth import InstallationStore, SlackOAuth, SlackOAuthError

    oauth = SlackOAuth(InstallationStore(), client=httpx.Client(transport=httpx.MockTransport(
        lambda _request: httpx.Response(200, json={
            "ok": True, "access_token": "xoxb", "bot_user_id": "B1",
            "team": {"id": "T1"},
        })
    )))
    state = oauth.create_install("acme", "worker", "owner")["state"]
    checks = 0

    async def recheck(_tenant, _worker):
        nonlocal checks
        checks += 1

    installation = await oauth.complete_install("code", state, recheck_worker=recheck)
    assert installation.tenant == "acme" and installation.worker_id == "worker"
    assert checks == 2
    with pytest.raises(SlackOAuthError):
        await oauth.complete_install("code", state, recheck_worker=recheck)


async def test_slack_oauth_rechecks_after_exchange_failure():
    import httpx
    from app.modules.channels.slack_oauth import InstallationStore, SlackOAuth, SlackOAuthError

    oauth = SlackOAuth(InstallationStore(), client=httpx.Client(transport=httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"ok": False, "error": "invalid_code"})
    )))
    state = oauth.create_install("acme", "worker", "owner")["state"]
    checks = 0

    async def recheck(_tenant, _worker):
        nonlocal checks
        checks += 1

    with pytest.raises(SlackOAuthError):
        await oauth.complete_install("bad", state, recheck_worker=recheck)
    assert checks == 2


async def test_salesforce_retry_stops_after_disable_during_refresh(monkeypatch):
    from app.modules.sales_intelligence.models import Opportunity, SalesforceConnection
    from app.modules.sales_intelligence.salesforce import SalesforceError, SalesforcePushService

    entered = threading.Event()
    release = threading.Event()
    enabled = True
    create_calls = 0
    connection = SalesforceConnection(
        tenant="acme", agent_id="worker", status="connected",
        access_token="token", instance_url="https://example.invalid",
    )

    class Auth:
        connections = type("Connections", (), {
            "update": staticmethod(lambda value: asyncio.sleep(0, result=value)),
        })()

        async def get_or_create_connection(self, _tenant, _agent_id):
            return connection

        def get_valid_access_token(self, _connection):
            return "expired"

        def refresh_access_token(self, _connection):
            entered.set()
            release.wait(timeout=5)
            return "fresh"

    async def recheck():
        if not enabled:
            raise WorkerUnavailable

    service = SalesforcePushService(auth=Auth())

    def create(*_args):
        nonlocal create_calls
        create_calls += 1
        if create_calls == 1:
            raise SalesforceError("401 unauthorized")
        return "SF-1"

    monkeypatch.setattr(service, "_create_opportunity", create)
    opportunity = Opportunity(
        id="o1", tenant="acme", agent_id="worker",
        external_id="ext-1", source_key="manual", source_name="Manual",
        title="Tender", stage="validated",
    )
    task = asyncio.create_task(service.push(
        opportunity, recheck_worker=recheck))
    assert await asyncio.to_thread(entered.wait, 5)
    enabled = False
    release.set()
    with pytest.raises(WorkerUnavailable):
        await task
    assert create_calls == 1


def test_slack_links_are_tenant_scoped():
    from app.modules.channels.slack_oauth import WorkspaceLinkStore

    links = WorkspaceLinkStore()
    links.link("acme", "T1", "U1", "worker-a")
    links.link("beta", "T1", "U1", "worker-b")
    assert links.resolve("acme", "T1", "U1") == "worker-a"
    assert links.resolve("beta", "T1", "U1") == "worker-b"
