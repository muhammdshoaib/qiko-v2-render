import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.deps import WorkerUnavailable
from app.modules.agentcore import batch_router
from app.modules.agentcore.models import AgentResult, Critique, Decision
from app.modules.agents.service import Agent, AgentService
from app.modules.ai.gateway import LLMResponse
from app.modules.chat.service import ChatService, ConversationScopeError
from app.modules.knowledge.models import Passage
from app.modules.voice.pipeline import VoicePipeline
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import StubProviderUnavailable, Worker, build_worker
from tests.helpers import auth_cookies


def _seed_agents(client) -> None:
    async def seed() -> None:
        await client.app.state.agents.store.add(Agent(id="enabled", tenant="acme", name="Enabled"))
        await client.app.state.agents.store.add(Agent(
            id="disabled", tenant="acme", name="Disabled", enabled=False
        ))
        await client.app.state.agents.store.add(Agent(id="other", tenant="beta", name="Other"))

    asyncio.run(seed())


@pytest.mark.parametrize(("path", "body"), [
    ("/api/v1/chat/ask", {"conversation_id": "c1", "question": "hello"}),
    ("/api/v1/chat/conversations", {"user_id": "u1"}),
    ("/api/v1/agents/batch-answer", {"questions": ["one"]}),
    ("/api/v1/agents/feedback", {"requirement_id": "r1", "approved_text": "ok"}),
    ("/api/v1/agents/batch-export", {"questions": ["one"]}),
    ("/api/v1/voice/speak", {"conversation_id": "c1", "audio_b64": "YQ=="}),
])
def test_generic_execution_requires_agent_id(client, path, body):
    response = client.post(path, json=body, cookies=auth_cookies("acme", "owner"))
    assert response.status_code == 422


def test_unavailable_worker_cases_are_indistinguishable(client, monkeypatch):
    _seed_agents(client)
    cookies = auth_cookies("acme", "owner")
    provider_calls = 0

    def provider(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not run")

    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", provider)
    responses = [
        client.post(
            "/api/v1/chat/ask",
            json={"conversation_id": "c1", "question": "hello", "agent_id": agent_id},
            cookies=cookies,
        )
        for agent_id in ("missing", "other", "disabled")
    ]
    assert {(response.status_code, response.text) for response in responses} == {
        (404, '{"detail":"worker not found"}')
    }
    assert provider_calls == 0


def test_conversation_and_feedback_reject_unavailable_before_write(client):
    _seed_agents(client)
    cookies = auth_cookies("acme", "owner")
    for agent_id in ("missing", "other", "disabled"):
        conversation = client.post(
            "/api/v1/chat/conversations",
            json={"user_id": "u1", "agent_id": agent_id}, cookies=cookies,
        )
        feedback = client.post(
            "/api/v1/agents/feedback",
            json={
                "requirement_id": "r1", "approved_text": "must not persist",
                "agent_id": agent_id,
            },
            cookies=cookies,
        )
        assert conversation.status_code == 404
        assert feedback.status_code == 404
        assert asyncio.run(client.app.state.chat.list_for_agent("acme", agent_id)) == []


async def test_conversation_scope_cannot_switch_agent():
    service = ChatService()

    async def available() -> None:
        return None

    await service.store.ensure_for_enabled_agent(
        "acme", "shared", user_id="u1", agent_id="a1", recheck_worker=available
    )
    with pytest.raises(ConversationScopeError):
        await service.store.ensure_for_enabled_agent(
            "acme", "shared", user_id="u1", agent_id="a2", recheck_worker=available
        )


async def test_chat_mid_run_disable_does_not_persist_assistant():
    service = ChatService()
    checks = 0

    async def recheck() -> None:
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise WorkerUnavailable

    worker = SimpleNamespace(
        config=SimpleNamespace(tenant="acme"),
        answer=lambda *_args, **_kwargs: asyncio.sleep(
            0, result=SimpleNamespace(answer="must not persist")
        ),
    )
    with pytest.raises(WorkerUnavailable):
        await service.ask(
            worker, "c1", "question", agent_id="a1", recheck_worker=recheck
        )
    history = await service.history("acme", "c1")
    assert history == []


async def test_batch_mid_run_disable_stops_later_calls(monkeypatch):
    provider_calls = 0
    checks = 0

    async def answer(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return SimpleNamespace(
            requirement_id="r1", answer="answer", confidence=1.0,
            decision=SimpleNamespace(value="pass"), citations=[],
        )

    async def recheck() -> None:
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise WorkerUnavailable

    async def resolve(*_args, **_kwargs):
        return SimpleNamespace(answer=answer), recheck

    monkeypatch.setattr(batch_router, "resolve_tenant_worker", resolve, raising=False)
    body = batch_router.BatchAskBody(questions=["one", "two", "three"], agent_id="a1")
    with pytest.raises(WorkerUnavailable):
        await batch_router._run_batch(None, "acme", body)
    assert provider_calls == 1


async def test_voice_mid_run_disable_prevents_tts():
    checks = 0
    synth_calls = 0

    async def recheck() -> None:
        nonlocal checks
        checks += 1
        if checks >= 4:
            raise WorkerUnavailable

    class Speech:
        def transcribe(self, _audio):
            return "question"

        def synthesize(self, _text):
            nonlocal synth_calls
            synth_calls += 1
            return b"audio"

    async def answer(*_args, **_kwargs):
        return SimpleNamespace(answer="answer")

    pipeline = VoicePipeline(Speech())
    with pytest.raises(WorkerUnavailable):
        await pipeline.speak(
            SimpleNamespace(answer=answer), "c1", b"audio", recheck_worker=recheck
        )
    assert synth_calls == 0


async def test_disable_during_retrieval_prevents_provider_call():
    agents = AgentService()
    await agents.store.add(Agent(id="a1", tenant="acme", name="A1"))
    entered = asyncio.Event()
    release = asyncio.Event()
    provider_calls = 0

    class Knowledge:
        async def retrieve(self, *_args, **_kwargs):
            entered.set()
            await release.wait()
            return []

    class Runtime:
        async def run(self, *_args, **_kwargs):
            nonlocal provider_calls
            provider_calls += 1
            return AgentResult("r1", "answer", Critique(1.0), Decision.auto_accept)

    async def recheck() -> None:
        agent = await agents.get("acme", "a1")
        if agent is None or not agent.enabled:
            raise WorkerUnavailable

    worker = Worker(WorkerConfig(name="A1", tenant="acme"), Knowledge(), Runtime())
    task = asyncio.create_task(worker.answer("r1", "question", recheck_worker=recheck))
    await entered.wait()
    await agents.set_enabled("acme", "a1", False, changed_by_email="admin.invalid")
    release.set()
    with pytest.raises(WorkerUnavailable):
        await task
    assert provider_calls == 0


async def test_disable_during_blocked_provider_discards_exchange():
    agents = AgentService()
    await agents.store.add(Agent(id="provider-a1", tenant="acme", name="A1"))
    entered = threading.Event()
    release = threading.Event()

    class Provider:
        def generate(self, _prompt, **_kwargs):
            entered.set()
            release.wait(timeout=5)
            return LLMResponse(text="answer", model="test", stub=False)

    async def recheck() -> None:
        agent = await agents.get("acme", "provider-a1")
        if agent is None or not agent.enabled:
            raise WorkerUnavailable

    worker = build_worker(
        WorkerConfig(name="A1", tenant="acme"), provider=Provider()
    )
    chat = ChatService()
    task = asyncio.create_task(chat.ask(
        worker, "provider-c1", "question", agent_id="provider-a1",
        recheck_worker=recheck,
    ))
    assert await asyncio.to_thread(entered.wait, 5)
    await agents.set_enabled(
        "acme", "provider-a1", False, changed_by_email="admin.invalid"
    )
    release.set()
    with pytest.raises(WorkerUnavailable):
        await task
    assert await chat.history("acme", "provider-c1") == []


async def test_stub_result_fails_closed():
    class Knowledge:
        async def retrieve(self, *_args, **_kwargs):
            return [Passage(id="p1", tenant="acme", doc_id="d1", text="context", embedding=[])]

    class Runtime:
        async def run(self, *_args, **_kwargs):
            return AgentResult(
                "r1", "plausible fallback", Critique(1.0), Decision.auto_accept, stub=True
            )

    async def available() -> None:
        return None

    worker = Worker(WorkerConfig(name="A1", tenant="acme"), Knowledge(), Runtime())
    with pytest.raises(StubProviderUnavailable):
        await worker.answer("r1", "question", recheck_worker=available)


def test_stub_http_response_is_503_and_chat_remains_empty(client, monkeypatch):
    class Provider:
        def generate(self, _prompt, **_kwargs):
            return LLMResponse(text="plausible fallback", model="stub", stub=True)

    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", lambda: Provider())
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="stub-worker", tenant="acme", name="Stub")
    ))
    response = client.post(
        "/api/v1/chat/ask",
        json={"conversation_id": "stub-c1", "question": "hello", "agent_id": "stub-worker"},
        cookies=auth_cookies("acme", "owner"),
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "answer generation is temporarily unavailable"}
    assert asyncio.run(client.app.state.chat.history("acme", "stub-c1")) == []


def test_evaluate_stub_response_is_503(client, monkeypatch):
    class Provider:
        def generate(self, _prompt, **_kwargs):
            return LLMResponse(text="fallback", model="stub", stub=True)

    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", lambda: Provider())
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="eval-stub", tenant="acme", name="Eval")
    ))
    client.post(
        "/api/v1/knowledge/ingest",
        json={"doc_id": "eval-doc", "text": "Evidence"},
        cookies=auth_cookies("acme", "owner"),
    )
    response = client.post(
        "/api/v1/knowledge/evaluate",
        json={"doc_id": "eval-doc", "criterion": "Check", "agent_id": "eval-stub"},
        cookies=auth_cookies("acme", "owner"),
    )
    assert response.status_code == 503


def test_public_chat_enabled_then_disabled_worker(client, monkeypatch):
    class Provider:
        def generate(self, prompt, **_kwargs):
            return LLMResponse(text=prompt, model="test", stub=False)

    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", lambda: Provider())
    async def seed() -> None:
        await client.app.state.agents.store.add(Agent(
            id="public-worker", tenant="publicco", name="Public", status="ready"
        ))

    asyncio.run(seed())
    body = {"tenant": "publicco", "worker_id": "public-worker", "question": "hello"}
    assert client.post("/api/v1/public/chat", json=body).status_code == 200
    asyncio.run(client.app.state.agents.set_enabled(
        "publicco", "public-worker", False, changed_by_email="admin.invalid"
    ))
    disabled = client.post("/api/v1/public/chat", json=body)
    missing = client.post(
        "/api/v1/public/chat",
        json={"tenant": "publicco", "worker_id": "missing", "question": "hello"},
    )
    assert (disabled.status_code, disabled.json()) == (missing.status_code, missing.json())


def test_batch_limits_reject_before_worker_resolution():
    with pytest.raises(ValueError):
        batch_router.BatchAskBody(questions=["q"] * 21, agent_id="a1")
    with pytest.raises(ValueError):
        batch_router.BatchAskBody(questions=["x" * 4001], agent_id="a1")
    with pytest.raises(ValueError):
        batch_router.BatchAskBody(questions=["x" * 2001] * 10, agent_id="a1")


def test_openapi_artifacts_require_agent_id(client):
    root = Path(__file__).parents[1]
    runtime = client.app.openapi()
    core_spec = json.loads((root / "openapi.json").read_text())
    client_spec = json.loads((root.parent / "frontend/packages/api-client/openapi.json").read_text())
    generated = (root.parent / "frontend/packages/api-client/src/schema.d.ts").read_text()

    assert runtime == core_spec == client_spec
    for schema_name in (
        "app__modules__chat__router__AskBody",
        "BatchAskBody",
        "app__modules__agentcore__batch_router__FeedbackBody",
        "SpeakBody",
    ):
        assert "agent_id" in runtime["components"]["schemas"][schema_name]["required"]
    assert generated.count("agent_id: string;") >= 5
