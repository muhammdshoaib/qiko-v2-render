import asyncio
from types import SimpleNamespace

import pytest

from app.core.deps import WorkerUnavailable
from app.modules.agentcore.models import AgentResult, Critique, Decision
from app.modules.assignments.service import QuestionAssignBody
from app.modules.agents.service import Agent
from app.modules.rfp import generation
from app.modules.rfp.service import PackAnswerService, RequirementService, RfpPackService
from app.modules.rfp.tree import PackTreeService
from app.tasks.jobs import generate_tender_artifacts

from tests.helpers import auth_cookies


def _seed_worker(client, tenant: str, agent_id: str, *, enabled: bool = True) -> None:
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=agent_id, tenant=tenant, name=agent_id, enabled=enabled)))


def _create_pack(client, tenant: str, agent_id: str = "w1") -> tuple[dict, dict]:
    _seed_worker(client, tenant, agent_id)
    cookies = auth_cookies(tenant, "owner")
    response = client.post("/api/v1/rfp/packs", cookies=cookies,
                           json={"agent_id": agent_id, "title": "Tender"})
    assert response.status_code == 200
    return cookies, response.json()


@pytest.mark.parametrize("tenant,agent_id", [
    ("create-missing", "missing"),
    ("create-cross", "foreign"),
    ("create-disabled", "disabled"),
])
def test_pack_create_rejects_unavailable_worker(client, tenant, agent_id):
    if agent_id == "foreign":
        _seed_worker(client, "other-tenant", agent_id)
    elif agent_id == "disabled":
        _seed_worker(client, tenant, agent_id, enabled=False)
    response = client.post("/api/v1/rfp/packs", cookies=auth_cookies(tenant, "owner"),
                           json={"agent_id": agent_id, "title": "Tender"})
    assert response.status_code == 404
    assert asyncio.run(client.app.state.rfp_packs.list(tenant)) == []


def test_disabled_worker_blocks_pack_mutations_and_lazy_tree_write(client):
    cookies, pack = _create_pack(client, "disabled-mutations")
    asyncio.run(client.app.state.requirements.save_extracted("disabled-mutations", pack["id"], [{
        "id": "A1", "title": "A", "classification": "KB", "requirement": "Answer A",
    }]))
    asyncio.run(client.app.state.agents.set_enabled(
        "disabled-mutations", "w1", False, changed_by_email="admin@invalid"))

    requests = [
        client.put(f"/api/v1/rfp/packs/{pack['id']}/stage", cookies=cookies,
                   json={"stage": "review"}),
        client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", cookies=cookies,
                   json={"outcome": "won"}),
        client.post(f"/api/v1/rfp/packs/{pack['id']}/confirm-assignments", cookies=cookies),
        client.get(f"/api/v1/rfp/packs/{pack['id']}/sections", cookies=cookies),
        client.delete(f"/api/v1/rfp/packs/{pack['id']}", cookies=cookies),
    ]
    assert [response.status_code for response in requests] == [404] * len(requests)
    assert asyncio.run(client.app.state.rfp_packs.get("disabled-mutations", pack["id"])).stage == "parsed"
    assert asyncio.run(client.app.state.pack_tree.sections.list("disabled-mutations", pack["id"])) == []


def test_disabled_worker_blocks_extract_chat_feedback_tree_and_generation(client, monkeypatch):
    cookies, pack = _create_pack(client, "disabled-matrix")
    asyncio.run(client.app.state.agents.set_enabled(
        "disabled-matrix", "w1", False, changed_by_email="admin@invalid"))
    provider_calls = []
    monkeypatch.setattr(
        "app.modules.rfp.router.get_provider",
        lambda **kwargs: provider_calls.append(kwargs) or pytest.fail("provider called"),
    )
    responses = [
        client.post(
            f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=cookies,
            files=[("files", ("tender.txt", b"Tender", "text/plain"))],
        ),
        client.post(
            f"/api/v1/rfp/packs/{pack['id']}/extract-url", cookies=cookies,
            json={"url": "https://example.invalid/tender"},
        ),
        client.post(
            f"/api/v1/rfp/packs/{pack['id']}/chat", cookies=cookies,
            json={"question": "Answer"},
        ),
        client.post(
            f"/api/v1/rfp/packs/{pack['id']}/feedback", cookies=cookies,
            json={"req_id": "A1", "decision": "Approve", "comment": "Approved"},
        ),
        client.post(
            f"/api/v1/rfp/packs/{pack['id']}/sections", cookies=cookies,
            json={"name": "Section"},
        ),
        client.post(f"/api/v1/rfp/packs/{pack['id']}/generate", cookies=cookies),
    ]
    assert [response.status_code for response in responses] == [404] * len(responses)
    persisted = asyncio.run(client.app.state.rfp_packs.get("disabled-matrix", pack["id"]))
    assert persisted.document_text == "" and persisted.source_documents == []
    assert asyncio.run(client.app.state.pack_tree.sections.list(
        "disabled-matrix", pack["id"])) == []
    assert provider_calls == []


def test_child_ids_are_scoped_to_exact_pack_and_provider_is_not_called(client, monkeypatch):
    cookies, first = _create_pack(client, "child-bola")
    second_response = client.post("/api/v1/rfp/packs", cookies=cookies,
                                  json={"agent_id": "w1", "title": "Other"})
    second = second_response.json()
    section = client.post(f"/api/v1/rfp/packs/{second['id']}/sections", cookies=cookies,
                          json={"name": "Other section"}).json()
    question = client.post(
        f"/api/v1/rfp/packs/{second['id']}/sections/{section['id']}/questions",
        cookies=cookies, json={"text": "Other question"}).json()
    provider_calls = 0

    def provider(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not be called")

    monkeypatch.setattr("app.modules.rfp.router.get_provider", provider)
    responses = [
        client.patch(f"/api/v1/rfp/packs/{first['id']}/sections/{section['id']}",
                     cookies=cookies, json={"name": "Injected"}),
        client.patch(f"/api/v1/rfp/packs/{first['id']}/questions/{question['id']}",
                     cookies=cookies, json={"text": "Injected"}),
        client.post(f"/api/v1/rfp/packs/{first['id']}/questions/{question['id']}/generate",
                    cookies=cookies),
    ]
    assert [response.status_code for response in responses] == [404, 404, 404]
    assert provider_calls == 0


def test_section_parent_must_be_in_same_pack_and_not_self(client):
    cookies, first = _create_pack(client, "parent-bola")
    second = client.post("/api/v1/rfp/packs", cookies=cookies,
                         json={"agent_id": "w1", "title": "Other"}).json()
    foreign_parent = client.post(f"/api/v1/rfp/packs/{second['id']}/sections", cookies=cookies,
                                 json={"name": "Foreign"}).json()
    assert client.post(f"/api/v1/rfp/packs/{first['id']}/sections", cookies=cookies,
                       json={"name": "Injected", "parent_id": foreign_parent["id"]}).status_code == 404
    local = client.post(f"/api/v1/rfp/packs/{first['id']}/sections", cookies=cookies,
                        json={"name": "Local"}).json()
    assert client.patch(f"/api/v1/rfp/packs/{first['id']}/sections/{local['id']}", cookies=cookies,
                        json={"parent_id": local["id"]}).status_code == 422


def test_outcome_store_failure_does_not_notify(client, monkeypatch):
    cookies, pack = _create_pack(client, "outcome-failure")
    notifications = []

    async def fail(*_args, **_kwargs):
        raise RuntimeError("write failed")

    async def notify(*args):
        notifications.append(args)

    monkeypatch.setattr(client.app.state.rfp_packs, "set_outcome_for_enabled_agent", fail)
    monkeypatch.setattr(client.app.state.teams_notifier, "notify", notify)
    with pytest.raises(RuntimeError):
        client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", cookies=cookies,
                   json={"outcome": "won"})
    assert notifications == []


def test_disabled_outcome_does_not_write_or_notify(client, monkeypatch):
    cookies, pack = _create_pack(client, "outcome-disabled")
    notifications = []

    async def notify(*args):
        notifications.append(args)

    monkeypatch.setattr(client.app.state.teams_notifier, "notify", notify)
    asyncio.run(client.app.state.agents.set_enabled(
        "outcome-disabled", "w1", False, changed_by_email="admin@invalid"))
    response = client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", cookies=cookies,
                          json={"outcome": "won"})
    assert response.status_code == 404
    assert asyncio.run(client.app.state.rfp_packs.get("outcome-disabled", pack["id"])).outcome is None
    assert notifications == []


def test_disabled_worker_blocks_assignment_write_and_reminder(client, monkeypatch):
    cookies, pack = _create_pack(client, "assignment-disabled")
    assignment = asyncio.run(client.app.state.assignments.bulk_assign(
        "assignment-disabled", "owner", pack_id=pack["id"], agent_id="w1",
        questions=[QuestionAssignBody(assignee_user_id="u1", question="Answer")]))[0]
    asyncio.run(client.app.state.agents.set_enabled(
        "assignment-disabled", "w1", False, changed_by_email="admin@invalid"))
    sends = []
    monkeypatch.setattr(
        "app.modules.assignments.router.get_email_sender",
        lambda: SimpleNamespace(send=lambda **kwargs: sends.append(kwargs)))

    status = client.put(f"/api/v1/assignments/{assignment.id}/status", cookies=cookies,
                        json={"status": "completed"})
    reminder = client.post("/api/v1/assignments/send-reminder", cookies=cookies, json={
        "pack_id": pack["id"], "assignee_user_id": "u1", "assignee_email": "u1@invalid",
    })
    assert status.status_code == 404
    assert reminder.status_code == 404
    assert asyncio.run(client.app.state.assignments.get(
        "assignment-disabled", assignment.id)).status == "pending"
    assert sends == []


async def test_queued_job_rejects_stale_agent_payload():
    packs, reqs, answers, tree = RfpPackService(), RequirementService(), PackAnswerService(), PackTreeService()
    pack = await packs.create("queue", "current", "Tender")
    await packs.set_document_text("queue", pack.id, "document")
    agents = SimpleNamespace(get=lambda *_args: None)
    with pytest.raises(WorkerUnavailable):
        await generate_tender_artifacts(
            tenant="queue", pack_id=pack.id, agent_id="stale", packs=packs, reqs=reqs,
            answers=answers, tree=tree, knowledge=None, agents=agents)


async def test_actual_disable_while_question_provider_blocked_persists_nothing(monkeypatch):
    packs, reqs, answers, tree = RfpPackService(), RequirementService(), PackAnswerService(), PackTreeService()
    pack = await packs.create("race", "worker", "Tender")
    await packs.set_document_text("race", pack.id, "document")
    enabled = True
    entered = asyncio.Event()
    release = asyncio.Event()

    class Agents:
        async def get(self, tenant, agent_id):
            return Agent(id=agent_id, tenant=tenant, name="Worker", enabled=enabled)

    async def extract(_text, *, recheck_worker=None):
        return [{"id": "A1", "title": "A", "classification": "KB",
                 "requirement": "Answer A", "subsections": []}]

    async def build(**_kwargs):
        class Worker:
            async def answer(self, rid, text, **_kwargs):
                entered.set()
                await release.wait()
                return AgentResult(requirement_id=rid, answer="must not persist",
                                   critique=Critique(grounding=0.9),
                                   decision=Decision.auto_accept, citations=["doc"], stub=False)
        return Worker()

    monkeypatch.setattr(generation, "extract_requirements_chunked", extract)
    monkeypatch.setattr(generation, "extract_brief", lambda *_args: {})
    monkeypatch.setattr(generation, "extract_compliance", lambda *_args: [])
    monkeypatch.setattr(generation, "get_provider", lambda **_kwargs: object())

    async def resolve(**kwargs):
        async def recheck():
            agent = await kwargs["agents"].get(kwargs["tenant"], kwargs["agent_id"])
            if not agent.enabled:
                raise WorkerUnavailable
        await recheck()
        return await build(), recheck

    monkeypatch.setattr(generation, "resolve_available_worker", resolve)
    task = asyncio.create_task(generation.run_generation(
        tenant="race", pack_id=pack.id, agent_id="worker", packs=packs, reqs=reqs,
        answers=answers, tree=tree, knowledge=None, agents=Agents()))
    await entered.wait()
    enabled = False
    release.set()
    with pytest.raises(WorkerUnavailable):
        await task
    questions = await tree.questions.list("race", pack.id)
    assert questions and questions[0].ai_answer == ""
