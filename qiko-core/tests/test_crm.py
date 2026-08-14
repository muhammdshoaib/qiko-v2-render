import json

import pytest

from app.modules.ai.gateway import LLMResponse
from app.modules.chat.service import ChatService
from app.modules.crm.service import CrmError, CrmService

from tests.helpers import auth_cookies


@pytest.fixture(autouse=True)
def _non_stub_provider(monkeypatch):
    class Provider:
        def generate(self, prompt, **_kwargs):
            return LLMResponse(text=prompt, model="test", stub=False)

    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", lambda: Provider())


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        return LLMResponse(text=self.text)


async def _seed_conversation(chat: ChatService, tenant="acme", agent_id="agent-1") -> str:
    cid = await chat.find_or_create(tenant, "visitor-1", agent_id)
    await chat.post(tenant, cid, "user", "Hi, I'm interested in your enterprise plan.")
    await chat.post(tenant, cid, "assistant", "Great! What's your team size?")
    return cid


# --- service ---
async def test_pipeline_lazily_creates_contacts_from_conversations():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)

    result = await crm.list_pipeline("acme", "agent-1")
    assert result["total"] == 1
    assert result["contacts"][0].status == "new"
    assert result["dashboard"]["status_breakdown"] == {"new": 1}


async def test_pipeline_does_not_duplicate_contacts_on_repeat_calls():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)

    await crm.list_pipeline("acme", "agent-1")
    result = await crm.list_pipeline("acme", "agent-1")
    assert result["total"] == 1


async def test_pipeline_is_tenant_and_agent_scoped():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat, tenant="acme", agent_id="agent-1")
    await _seed_conversation(chat, tenant="acme", agent_id="agent-2")
    await _seed_conversation(chat, tenant="beta", agent_id="agent-1")

    assert (await crm.list_pipeline("acme", "agent-1"))["total"] == 1
    assert (await crm.list_pipeline("acme", "agent-2"))["total"] == 1
    assert (await crm.list_pipeline("beta", "agent-1"))["total"] == 1
    assert (await crm.list_pipeline("acme", "agent-3"))["total"] == 0


async def test_get_detail_returns_real_timeline_from_chat_history():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)
    result = await crm.list_pipeline("acme", "agent-1")
    contact_id = result["contacts"][0].id

    detail = await crm.get_detail("acme", contact_id)
    assert len(detail["timeline"]) == 2
    assert detail["timeline"][0]["summary"] == "Hi, I'm interested in your enterprise plan."
    assert detail["stats"]["message_count"] == 1  # only the user turn counts


async def test_get_detail_404_for_missing_contact():
    crm = CrmService(ChatService())
    with pytest.raises(CrmError):
        await crm.get_detail("acme", "missing")


async def test_update_contact_fields_and_pipeline_stage():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)
    contact_id = (await crm.list_pipeline("acme", "agent-1"))["contacts"][0].id

    updated = await crm.update_contact("acme", contact_id, name="Jane Doe", email="jane@invalid",
                                       status="interested", estimated_value=50000)
    assert updated.name == "Jane Doe" and updated.email == "jane@invalid"
    assert updated.status == "interested" and updated.estimated_value == 50000


async def test_update_contact_rejects_invalid_pipeline_stage():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)
    contact_id = (await crm.list_pipeline("acme", "agent-1"))["contacts"][0].id
    with pytest.raises(CrmError):
        await crm.update_contact("acme", contact_id, status="not-a-real-stage")


async def test_generate_summary_parses_llm_json():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)
    contact_id = (await crm.list_pipeline("acme", "agent-1"))["contacts"][0].id

    canned = json.dumps({"summary": "Wants enterprise pricing for a 50-person team.",
                         "sentiment": "positive", "key_topics": ["pricing", "enterprise"]})
    updated = await crm.generate_summary("acme", contact_id, _CannedProvider(canned))
    assert updated.ai_summary == "Wants enterprise pricing for a 50-person team."
    assert updated.sentiment == "positive"
    assert updated.key_topics == ["pricing", "enterprise"]


async def test_generate_summary_rejects_non_json():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)
    contact_id = (await crm.list_pipeline("acme", "agent-1"))["contacts"][0].id
    with pytest.raises(CrmError):
        await crm.generate_summary("acme", contact_id, _CannedProvider("not json"))


async def test_add_and_update_action():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)
    contact_id = (await crm.list_pipeline("acme", "agent-1"))["contacts"][0].id

    action = await crm.add_action("acme", contact_id, title="Send pricing sheet", priority="high")
    assert action.status == "pending" and action.priority == "high"

    done = await crm.update_action_status("acme", action.id, "done")
    assert done.status == "done"


async def test_update_action_rejects_invalid_status():
    chat = ChatService()
    crm = CrmService(chat)
    await _seed_conversation(chat)
    contact_id = (await crm.list_pipeline("acme", "agent-1"))["contacts"][0].id
    action = await crm.add_action("acme", contact_id, title="Follow up")
    with pytest.raises(CrmError):
        await crm.update_action_status("acme", action.id, "bogus")


# --- API-level ---
def _create_agent(client, cookies, name: str) -> str:
    return client.post("/api/v1/agents", cookies=cookies, json={"name": name}).json()["id"]


def test_crm_pipeline_round_trip_via_api(client):
    cookies = auth_cookies(tenant="acme")
    agent_id = _create_agent(client, cookies, "CRM")
    # A conversation must be created with its agent_id set (as the embed widget/dashboard test
    # chat both do via /chat/conversations) before /ask -- asking with a bare, never-created
    # conversation_id would default it to a generic "public" agent, not the one being tested.
    conv = client.post("/api/v1/chat/conversations", cookies=cookies,
                       json={"user_id": "visitor-9", "agent_id": agent_id})
    assert conv.status_code == 200
    conversation_id = conv.json()["conversation_id"]
    ask_resp = client.post("/api/v1/chat/ask", cookies=cookies,
                           json={"conversation_id": conversation_id, "agent_id": agent_id, "question": "Hi there"})
    assert ask_resp.status_code == 200

    pipeline = client.get(f"/api/v1/crm/{agent_id}", cookies=cookies)
    assert pipeline.status_code == 200
    body = pipeline.json()
    assert body["total"] == 1
    contact_id = body["contacts"][0]["id"]

    detail = client.get(f"/api/v1/crm/contacts/{contact_id}", cookies=cookies)
    assert detail.status_code == 200
    assert len(detail.json()["timeline"]) >= 1

    patch = client.patch(f"/api/v1/crm/contacts/{contact_id}", cookies=cookies,
                         json={"name": "Jane Doe", "status": "contacted"})
    assert patch.status_code == 200
    assert patch.json()["name"] == "Jane Doe" and patch.json()["status"] == "contacted"

    action = client.post(f"/api/v1/crm/contacts/{contact_id}/actions", cookies=cookies,
                         json={"title": "Call back tomorrow"})
    assert action.status_code == 200
    action_id = action.json()["id"]

    update = client.patch(f"/api/v1/crm/actions/{action_id}", cookies=cookies, json={"status": "done"})
    assert update.status_code == 200 and update.json()["status"] == "done"


def test_crm_only_materializes_public_chat_conversations(client):
    cookies = auth_cookies(tenant="acme")
    agent_id = _create_agent(client, cookies, "CRM chat origin")
    assert client.post(f"/api/v1/agents/{agent_id}/ready", cookies=cookies).status_code == 200

    internal_chat = client.post("/api/v1/chat/ask", cookies=cookies, json={
        "conversation_id": "worker-test-conversation", "agent_id": agent_id, "question": "Internal test",
    })
    assert internal_chat.status_code == 200
    after_internal = client.get(f"/api/v1/crm/{agent_id}", cookies=cookies)
    assert after_internal.status_code == 200

    public_chat = client.post("/api/v1/public/chat", json={
        "tenant": "acme", "worker_id": agent_id, "question": "Public chat",
    })
    assert public_chat.status_code == 200
    forged_marker = client.post("/api/v1/public/chat", json={
        "tenant": "acme", "worker_id": agent_id, "user_email": "public", "question": "Public marker",
    })
    assert forged_marker.status_code == 200
    after_public = client.get(f"/api/v1/crm/{agent_id}", cookies=cookies)
    assert after_public.status_code == 200

    assert after_internal.json()["total"] == 0
    assert after_public.json()["total"] == 2


def test_crm_contact_detail_404_for_missing_contact(client):
    cookies = auth_cookies(tenant="acme")
    resp = client.get("/api/v1/crm/contacts/missing", cookies=cookies)
    assert resp.status_code == 404


def test_crm_update_contact_requires_editor_role(client):
    viewer_cookies = auth_cookies(tenant="acme", role="viewer")
    owner_cookies = auth_cookies(tenant="acme", role="owner")
    agent_id = _create_agent(client, owner_cookies, "CRM RBAC")
    conv = client.post("/api/v1/chat/conversations", cookies=owner_cookies,
                       json={"user_id": "visitor-rbac", "agent_id": agent_id})
    conversation_id = conv.json()["conversation_id"]
    client.post("/api/v1/chat/ask", cookies=owner_cookies,
               json={"conversation_id": conversation_id, "agent_id": agent_id, "question": "Hi"})
    contact_id = client.get(f"/api/v1/crm/{agent_id}", cookies=owner_cookies).json()["contacts"][0]["id"]

    resp = client.patch(f"/api/v1/crm/contacts/{contact_id}", cookies=viewer_cookies, json={"name": "x"})
    assert resp.status_code == 403


def test_crm_sync_salesforce_requires_credentials_on_the_contacts_worker(client):
    cookies = auth_cookies(tenant="acme")
    # A real Agent record (not just any conversation's agent_id) with no Salesforce connection.
    agent_id = client.post("/api/v1/agents", json={"name": "IDG"}, cookies=cookies).json()["id"]
    conv = client.post("/api/v1/chat/conversations", cookies=cookies, json={"user_id": "visitor-sf", "agent_id": agent_id})
    conversation_id = conv.json()["conversation_id"]
    client.post("/api/v1/chat/ask", cookies=cookies,
               json={"conversation_id": conversation_id, "agent_id": agent_id, "question": "Hi"})
    contact_id = client.get(f"/api/v1/crm/{agent_id}", cookies=cookies).json()["contacts"][0]["id"]

    resp = client.post(f"/api/v1/crm/contacts/{contact_id}/sync-salesforce", cookies=cookies)
    assert resp.status_code == 422


def test_crm_sync_salesforce_pushes_a_lead(client, monkeypatch):
    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def create_lead(self, **kwargs):
            return {"id": "00Q1", "success": True}

    monkeypatch.setattr("app.integrations.clients.SalesforceClient", _FakeClient)
    cookies = auth_cookies(tenant="acme")
    # The agent must exist as a real Agent record (not just any conversation's agent_id) so the
    # sync endpoint can look up its Salesforce credentials.
    agent = client.post("/api/v1/agents", json={"name": "IDG Sales"}, cookies=cookies).json()
    agent_id = agent["id"]
    client.post(f"/api/v1/agents/{agent_id}/salesforce-credentials", cookies=cookies, json={
        "client_id": "cid", "client_secret": "secret", "instance_url": "https://acme.my.salesforce.com",
    })
    conv = client.post("/api/v1/chat/conversations", cookies=cookies, json={"user_id": "visitor-sf2", "agent_id": agent_id})
    conversation_id = conv.json()["conversation_id"]
    client.post("/api/v1/chat/ask", cookies=cookies,
               json={"conversation_id": conversation_id, "agent_id": agent_id, "question": "Hi"})
    contact_id = client.get(f"/api/v1/crm/{agent_id}", cookies=cookies).json()["contacts"][0]["id"]

    resp = client.post(f"/api/v1/crm/contacts/{contact_id}/sync-salesforce", cookies=cookies)
    assert resp.status_code == 200
    assert resp.json() == {"synced": True, "salesforce_id": "00Q1"}


def test_crm_pipeline_is_isolated_across_tenants(client):
    cookies = auth_cookies(tenant="acme")
    agent_id = _create_agent(client, cookies, "CRM isolated")
    conv = client.post("/api/v1/chat/conversations", cookies=cookies,
                       json={"user_id": "visitor-shared", "agent_id": agent_id})
    conversation_id = conv.json()["conversation_id"]
    client.post("/api/v1/chat/ask", cookies=cookies,
               json={"conversation_id": conversation_id, "agent_id": agent_id, "question": "Hi"})
    other_tenant = client.get(f"/api/v1/crm/{agent_id}", cookies=auth_cookies(tenant="beta"))
    assert other_tenant.json()["total"] == 0
