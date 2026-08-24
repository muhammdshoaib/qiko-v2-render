"""Tests for the Intelligence Worker chat module and endpoints."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.agents.service import Agent
from app.modules.ai.gateway import LLMResponse
from app.modules.channels.slack_store import SlackMessage
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import build_worker
from tests.helpers import auth_cookies

C = auth_cookies("intelco", "owner")


def _seed_worker(client, tenant="intelco", agent_id="w1"):
    if asyncio.run(client.app.state.agents.get(tenant, agent_id)) is None:
        asyncio.run(client.app.state.agents.store.add(
            Agent(id=agent_id, tenant=tenant, name="Worker")))


def _ingest_slack_message(client, text, ts="1700000000.100000"):
    msg = SlackMessage(
        tenant="intelco", agent_id="w1", team_id="T1", channel_id="C1",
        channel_type="channel", thread_ts=None, user_id="U1", text=text, ts=ts)
    asyncio.run(client.app.state.slack_messages.add(msg))


class _Provider:
    """Fake provider that returns a structured JSON answer."""

    def generate(self, prompt, **_kwargs):
        return LLMResponse(text=json.dumps({
            "answer": "We decided to keep pricing flat.",
            "confidence": 0.92,
            "gaps": "",
        }), model="test", stub=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", _Provider)
    app = create_app()
    with TestClient(app) as c:
        _seed_worker(c)
        yield c


def test_ask_returns_answer_with_source_links(client):
    _ingest_slack_message(client, "we decided to keep pricing flat")
    r = client.post(
        "/api/v1/intelligence/agents/w1/chat/ask",
        cookies=C,
        json={"question": "what did we decide about pricing?"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "pricing flat" in data["reply"].lower()
    assert data["passages_used"] == 1
    assert len(data["sources"]) == 1
    assert "app.slack.com" in data["sources"][0]
    assert data["intent"] == "data"
    assert data["conversation_id"]


def test_ask_without_supporting_signals_returns_no_data(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/chat/ask",
        cookies=C,
        json={"question": "what is the CEO's favourite colour?"},
    )
    assert r.status_code == 200
    assert r.json()["reply"] == "I don't have that data."
    assert r.json()["passages_used"] == 0
    assert r.json()["sources"] == []


def test_greeting_is_answered_without_model_call(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/chat/ask",
        cookies=C,
        json={"question": "hello"},
    )
    assert r.status_code == 200
    assert r.json()["intent"] == "greeting"
    assert "intelligence worker" in r.json()["reply"].lower()
    assert r.json()["passages_used"] == 0


def test_history_persists_exchange(client):
    _ingest_slack_message(client, "we decided to keep pricing flat")
    r = client.post(
        "/api/v1/intelligence/agents/w1/chat/ask",
        cookies=C,
        json={"question": "what did we decide about pricing?", "conversation_id": "conv-1"},
    )
    assert r.status_code == 200
    cid = r.json()["conversation_id"]

    r = client.get(f"/api/v1/intelligence/agents/w1/chat/{cid}/history", cookies=C)
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert "pricing" in history[0]["text"].lower()
    assert history[1]["role"] == "assistant"


def test_ask_forbids_viewer(client):
    r = client.post(
        "/api/v1/intelligence/agents/w1/chat/ask",
        cookies=auth_cookies("intelco", "viewer"),
        json={"question": "hello"},
    )
    assert r.status_code == 403


def test_history_allows_viewer(client):
    _seed_worker(client)
    _ingest_slack_message(client, "we decided to keep pricing flat")
    client.post(
        "/api/v1/intelligence/agents/w1/chat/ask",
        cookies=C,
        json={"question": "what did we decide about pricing?", "conversation_id": "conv-2"},
    )
    r = client.get("/api/v1/intelligence/agents/w1/chat/conv-2/history",
                   cookies=auth_cookies("intelco", "viewer"))
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_intelligence_chat_unit_returns_sources_for_grounded_question():
    """Direct unit test: fake provider, controlled passages, citation URLs come back."""
    from app.modules.intelligence.chat import IntelligenceChat
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.knowledge.store import InMemoryVectorStore

    knowledge = KnowledgeService(store=InMemoryVectorStore())
    worker = build_worker(
        WorkerConfig(name="w1", tenant="intelco", agent_id="w1"),
        provider=_Provider(), knowledge=knowledge,
    )
    asyncio.run(knowledge.ingest(
        "intelco", "https://app.slack.com/client/T1/C1/1700000000.100000",
        "Slack message from U1 in T1/C1\n\nwe decided to keep pricing flat",
        agent_id="w1"))

    chat = IntelligenceChat(worker)
    result = asyncio.run(chat.answer("what did we decide about pricing?"))
    assert "pricing flat" in result["reply"].lower()
    assert result["sources"] == ["https://app.slack.com/client/T1/C1/1700000000.100000"]
    assert result["passages_used"] == 1
    assert result["intent"] == "data"


def test_intelligence_chat_unit_honours_no_data_for_missing_signals():
    from app.modules.intelligence.chat import IntelligenceChat
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.knowledge.store import InMemoryVectorStore

    knowledge = KnowledgeService(store=InMemoryVectorStore())
    worker = build_worker(
        WorkerConfig(name="w1", tenant="intelco", agent_id="w1"),
        provider=_Provider(), knowledge=knowledge,
    )
    chat = IntelligenceChat(worker)
    result = asyncio.run(chat.answer("what is the CEO's favourite colour?"))
    assert result["reply"] == "I don't have that data."
    assert result["passages_used"] == 0
    assert result["sources"] == []
    assert result["intent"] == "data"


def test_intelligence_chat_unit_answers_sprint_landing_from_metrics():
    from app.modules.intelligence.chat import IntelligenceChat
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.knowledge.store import InMemoryVectorStore

    knowledge = KnowledgeService(store=InMemoryVectorStore())
    worker = build_worker(
        WorkerConfig(name="w1", tenant="intelco", agent_id="w1"),
        provider=_Provider(), knowledge=knowledge,
    )

    async def _metrics():
        return {
            "QIW": {
                "available": True,
                "window": {"key": "14d", "from": "2026-08-01T00:00:00Z", "to": "2026-08-15T00:00:00Z"},
                "sprint": {
                    "number": 2,
                    "name": "Sprint 2",
                    "state": "active",
                    "committed": {"tickets": 10, "points": 20},
                    "done": {"tickets": 5, "points": 10},
                    "projectedCarryOver": {"tickets": 2, "points": 4},
                },
            },
        }

    chat = IntelligenceChat(worker)
    result = asyncio.run(chat.answer(
        "is this sprint going to land?", metrics_provider=_metrics))
    assert result["intent"] == "sprint_landing"
    assert "5 of 10" in result["reply"]
    assert "2 are projected to carry over" in result["reply"]
    assert result["passages_used"] == 0
    assert result["sources"] == []


def test_intelligence_chat_unit_declines_sprint_landing_without_metrics():
    from app.modules.intelligence.chat import IntelligenceChat
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.knowledge.store import InMemoryVectorStore

    knowledge = KnowledgeService(store=InMemoryVectorStore())
    worker = build_worker(
        WorkerConfig(name="w1", tenant="intelco", agent_id="w1"),
        provider=_Provider(), knowledge=knowledge,
    )
    chat = IntelligenceChat(worker)
    result = asyncio.run(chat.answer("is this sprint going to land?"))
    assert result["intent"] == "sprint_landing"
    assert result["reply"] == "I don't have that data."
    assert result["passages_used"] == 0


def test_intelligence_chat_unit_lists_qiko_track_projects():
    from app.modules.intelligence.chat import IntelligenceChat
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.knowledge.store import InMemoryVectorStore

    knowledge = KnowledgeService(store=InMemoryVectorStore())
    worker = build_worker(
        WorkerConfig(name="w1", tenant="intelco", agent_id="w1"),
        provider=_Provider(), knowledge=knowledge,
    )

    async def _metrics():
        return {
            "QIW": {"available": True},
            "PROJ": {"available": True},
        }

    chat = IntelligenceChat(worker)
    result = asyncio.run(chat.answer(
        "e proiecte avem în Qiko Track?", metrics_provider=_metrics))
    assert result["intent"] == "list_projects"
    assert "QIW" in result["reply"]
    assert "PROJ" in result["reply"]
    assert result["passages_used"] == 0
    assert result["sources"] == []


def test_intelligence_chat_unit_declines_project_list_without_metrics():
    from app.modules.intelligence.chat import IntelligenceChat
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.knowledge.store import InMemoryVectorStore

    knowledge = KnowledgeService(store=InMemoryVectorStore())
    worker = build_worker(
        WorkerConfig(name="w1", tenant="intelco", agent_id="w1"),
        provider=_Provider(), knowledge=knowledge,
    )
    chat = IntelligenceChat(worker)
    result = asyncio.run(chat.answer("what projects do we have in Qiko Track?"))
    assert result["intent"] == "list_projects"
    assert result["reply"] == "I don't have that data."
    assert result["passages_used"] == 0


def test_intelligence_chat_unit_answers_qiko_track_access():
    from app.modules.intelligence.chat import IntelligenceChat
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.knowledge.store import InMemoryVectorStore

    knowledge = KnowledgeService(store=InMemoryVectorStore())
    worker = build_worker(
        WorkerConfig(name="w1", tenant="intelco", agent_id="w1"),
        provider=_Provider(), knowledge=knowledge,
    )

    async def _metrics():
        return {
            "QIW": {"available": True},
            "PROJ": {"available": False, "error": "token is invalid or expired"},
        }

    chat = IntelligenceChat(worker)
    result = asyncio.run(chat.answer(
        "ai access in Qiko Track?", metrics_provider=_metrics))
    assert result["intent"] == "qiko_track_access"
    assert "QIW" in result["reply"]
    assert "PROJ" not in result["reply"]
    assert "Yes" in result["reply"]
    assert result["passages_used"] == 0
    assert result["sources"] == []


def test_intelligence_chat_unit_declines_qiko_track_access_without_metrics():
    from app.modules.intelligence.chat import IntelligenceChat
    from app.modules.knowledge.service import KnowledgeService
    from app.modules.knowledge.store import InMemoryVectorStore

    knowledge = KnowledgeService(store=InMemoryVectorStore())
    worker = build_worker(
        WorkerConfig(name="w1", tenant="intelco", agent_id="w1"),
        provider=_Provider(), knowledge=knowledge,
    )
    chat = IntelligenceChat(worker)
    result = asyncio.run(chat.answer("do you have access to Qiko Track?"))
    assert result["intent"] == "qiko_track_access"
    assert result["reply"] == "I don't have that data."
    assert result["passages_used"] == 0
