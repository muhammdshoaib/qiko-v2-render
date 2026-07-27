import asyncio

import pytest

from app.modules.agents.service import Agent
from app.modules.assignments.service import (
    AssignmentError,
    AssignmentService,
    QuestionAssignBody,
    SectionAssignBody,
)
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.store import User

from tests.helpers import auth_cookies


# --- service-level ---
async def test_bulk_assign_sections_and_questions():
    svc = AssignmentService()
    saved = await svc.bulk_assign(
        "idg", "owner-1", pack_id="pack1", agent_id="w1", rfp_title="Tender X",
        sections=[SectionAssignBody(section_id="B1", assignee_user_id="u1",
                                    questions=["Q1", "Q2"], title="Org Structure")],
        questions=[QuestionAssignBody(assignee_user_id="u2", question="Standalone Q")])
    assert len(saved) == 3
    assert saved[0].section_id == "B1" and saved[0].assignee_user_id == "u1"
    assert saved[2].section_id is None and saved[2].assignee_user_id == "u2"


async def test_bulk_assign_requires_at_least_one_item():
    svc = AssignmentService()
    with pytest.raises(AssignmentError):
        await svc.bulk_assign("idg", "owner-1", pack_id="pack1", agent_id="w1")


async def test_dashboard_rollup():
    svc = AssignmentService()
    await svc.bulk_assign("idg", "owner-1", pack_id="pack1", agent_id="w1",
                          sections=[SectionAssignBody(section_id="B1", assignee_user_id="u1",
                                                      questions=["Q1", "Q2"], title="Org")])
    items = await svc.list("idg", pack_id="pack1", assignee_user_id="u1")
    await svc.update_status("idg", items[0].id, "completed")

    rows = await svc.dashboard("idg", "pack1", ["u1", "u2"])
    u1 = next(r for r in rows if r["user_id"] == "u1")
    assert u1["assigned"] == 2 and u1["completed"] == 1 and u1["progress"] == 50
    u2 = next(r for r in rows if r["user_id"] == "u2")
    assert u2["assigned"] == 0 and u2["status"] == "completed"  # no items = trivially done


async def test_delete_by_section_and_pack():
    svc = AssignmentService()
    await svc.bulk_assign("idg", "owner-1", pack_id="pack1", agent_id="w1",
                          sections=[SectionAssignBody(section_id="B1", assignee_user_id="u1",
                                                      questions=["Q1"], title="Org")])
    assert await svc.delete_by_section("idg", "pack1", "B1") == 1
    await svc.bulk_assign("idg", "owner-1", pack_id="pack1", agent_id="w1",
                          questions=[QuestionAssignBody(assignee_user_id="u1", question="Q")])
    assert await svc.delete_by_pack("idg", "pack1") == 1


# --- API-level ---
def _seed_user(user_id: str, tenant: str, *, email: str | None = None) -> None:
    get_store().seed(User(id=user_id, email=email if email is not None else f"{user_id}@invalid",
                          password_hash="x", tenant=tenant, role=Role.viewer))


def _seed_pack_tree(client, *, tenant: str, agent_id: str = "w1", title: str = "Tender X") -> dict:
    if asyncio.run(client.app.state.agents.get(tenant, agent_id)) is None:
        asyncio.run(client.app.state.agents.store.add(
            Agent(id=agent_id, tenant=tenant, name="Worker")))
    admin = auth_cookies(tenant, "owner", user_id=f"{tenant}-admin")
    pack = client.post("/api/v1/rfp/packs", cookies=admin,
                       json={"agent_id": agent_id, "title": title}).json()
    parent = client.post(f"/api/v1/rfp/packs/{pack['id']}/sections", cookies=admin,
                         json={"code": "A", "name": "Trusted parent"}).json()
    leaf = client.post(f"/api/v1/rfp/packs/{pack['id']}/sections", cookies=admin,
                       json={"code": "A.1", "name": "Trusted leaf", "parent_id": parent["id"]}).json()
    client.post(f"/api/v1/rfp/packs/{pack['id']}/sections/{leaf['id']}/questions", cookies=admin,
                json={"text": "Trusted persisted question"})
    return {"admin": admin, "pack": pack, "parent": parent, "leaf": leaf}


def _section_assignment_payload(seed: dict, *, assignee: str, **overrides) -> dict:
    payload = {
        "pack_id": seed["pack"]["id"],
        "agent_id": seed["pack"]["agent_id"],
        "rfp_title": "Untrusted title",
        "sections": [{
            "section_id": seed["leaf"]["id"],
            "assignee_user_id": assignee,
            "questions": ["Untrusted question"],
            "title": "Untrusted section",
        }],
    }
    payload.update(overrides)
    return payload


def test_assignments_api_bulk_and_dashboard_derives_persisted_section_data(client):
    seed = _seed_pack_tree(client, tenant="assignco")
    _seed_user("u1", "assignco")
    _seed_user("u2", "assignco")
    payload = _section_assignment_payload(seed, assignee="u1")
    payload["questions"] = [{"assignee_user_id": "u2", "question": "Standalone"}]

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json=payload)
    assert r.status_code == 200 and len(r.json()) == 2
    section_assignment = r.json()[0]
    assert section_assignment["section_title"] == "Trusted leaf"
    assert section_assignment["question"] == "Trusted persisted question"
    assert section_assignment["rfp_title"] == "Tender X"

    listed = client.get("/api/v1/assignments", params={"pack_id": seed["pack"]["id"]},
                        cookies=seed["admin"]).json()
    assert len(listed) == 2
    dash = client.get("/api/v1/assignments/dashboard",
                      params={"pack_id": seed["pack"]["id"], "member_user_ids": "u1,u2"},
                      cookies=seed["admin"]).json()
    assert next(row for row in dash if row["user_id"] == "u1")["assigned"] == 1


def test_assignments_api_rejects_parent_section(client):
    seed = _seed_pack_tree(client, tenant="assignparent")
    _seed_user("parent-user", "assignparent")
    payload = _section_assignment_payload(seed, assignee="parent-user")
    payload["sections"][0]["section_id"] = seed["parent"]["id"]

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json=payload)
    assert r.status_code == 422
    assert "leaf" in r.json()["detail"].lower()


def test_assignments_api_rejects_section_from_another_pack(client):
    seed = _seed_pack_tree(client, tenant="assigncrosspack")
    other = _seed_pack_tree(client, tenant="assigncrosspack", title="Other tender")
    _seed_user("crosspack-user", "assigncrosspack")
    payload = _section_assignment_payload(seed, assignee="crosspack-user")
    payload["sections"][0]["section_id"] = other["leaf"]["id"]

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json=payload)
    assert r.status_code == 404


def test_assignments_api_rejects_agent_mismatch(client):
    seed = _seed_pack_tree(client, tenant="assignagent", agent_id="persisted-agent")
    _seed_user("agent-user", "assignagent")
    payload = _section_assignment_payload(seed, assignee="agent-user", agent_id="spoofed-agent")

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json=payload)
    assert r.status_code == 422
    assert "agent" in r.json()["detail"].lower()


def test_assignments_api_rejects_cross_tenant_assignee(client):
    seed = _seed_pack_tree(client, tenant="assignassignee")
    _seed_user("foreign-user", "different-tenant")

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"],
                    json=_section_assignment_payload(seed, assignee="foreign-user"))
    assert r.status_code == 404
    assert "assignee" in r.json()["detail"].lower()


def test_assignments_api_rejects_nonexistent_pack_for_standalone_question(client):
    tenant = "assignstandalone-missing"
    admin = auth_cookies(tenant, "owner", user_id=f"{tenant}-admin")
    _seed_user("standalone-user", tenant)

    r = client.post("/api/v1/assignments/bulk", cookies=admin, json={
        "pack_id": "missing-pack",
        "agent_id": "w1",
        "questions": [{"assignee_user_id": "standalone-user", "question": "Question"}],
    })
    assert r.status_code == 404
    assert "pack" in r.json()["detail"].lower()


def test_assignments_api_rejects_agent_mismatch_for_standalone_question(client):
    seed = _seed_pack_tree(client, tenant="assignstandalone-agent", agent_id="persisted-agent")
    _seed_user("standalone-agent-user", "assignstandalone-agent")

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json={
        "pack_id": seed["pack"]["id"],
        "agent_id": "spoofed-agent",
        "questions": [{"assignee_user_id": "standalone-agent-user", "question": "Question"}],
    })
    assert r.status_code == 422
    assert "agent" in r.json()["detail"].lower()


def test_assignments_api_rejects_cross_tenant_assignee_for_standalone_question(client):
    seed = _seed_pack_tree(client, tenant="assignstandalone")
    _seed_user("standalone-foreign", "different-tenant")

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json={
        "pack_id": seed["pack"]["id"],
        "agent_id": seed["pack"]["agent_id"],
        "questions": [{"assignee_user_id": "standalone-foreign", "question": "Question"}],
    })
    assert r.status_code == 404
    assert "assignee" in r.json()["detail"].lower()


def test_assignments_api_valid_standalone_uses_persisted_pack_metadata(client):
    seed = _seed_pack_tree(client, tenant="assignstandalone-valid", agent_id="trusted-agent",
                           title="Trusted tender")
    _seed_user("standalone-valid-user", "assignstandalone-valid")

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json={
        "pack_id": seed["pack"]["id"],
        "agent_id": "trusted-agent",
        "rfp_title": "Untrusted tender",
        "questions": [{"assignee_user_id": "standalone-valid-user", "question": "Standalone"}],
    })
    assert r.status_code == 200
    assert r.json()[0]["agent_id"] == "trusted-agent"
    assert r.json()[0]["rfp_title"] == "Trusted tender"
    assert r.json()[0]["question"] == "Standalone"


def test_assignments_api_rejects_leaf_without_questions(client):
    seed = _seed_pack_tree(client, tenant="assignempty")
    _seed_user("empty-user", "assignempty")
    empty_leaf = client.post(f"/api/v1/rfp/packs/{seed['pack']['id']}/sections", cookies=seed["admin"],
                             json={"code": "B", "name": "Empty leaf"}).json()
    payload = _section_assignment_payload(seed, assignee="empty-user")
    payload["sections"][0]["section_id"] = empty_leaf["id"]

    r = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json=payload)
    assert r.status_code == 422
    assert "questions" in r.json()["detail"].lower()


def test_assignments_bulk_requires_admin_role(client):
    viewer = auth_cookies("assignco2", "viewer")
    r = client.post("/api/v1/assignments/bulk", cookies=viewer,
                    json={"pack_id": "p", "agent_id": "w1",
                          "questions": [{"assignee_user_id": "x", "question": "Q"}]})
    assert r.status_code == 403


def test_assignee_can_update_own_status_but_not_reassign(client):
    seed = _seed_pack_tree(client, tenant="assignco3")
    _seed_user("u1", "assignco3")
    _seed_user("u2", "assignco3")
    created = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json={
        "pack_id": seed["pack"]["id"], "agent_id": "w1",
        "questions": [{"assignee_user_id": "u1", "question": "Q"}],
    }).json()
    assignment_id = created[0]["id"]

    other = auth_cookies("assignco3", "viewer", user_id="other-user")
    assert client.put(f"/api/v1/assignments/{assignment_id}/status", cookies=other,
                      json={"status": "completed"}).status_code == 403

    assignee = auth_cookies("assignco3", "viewer", user_id="u1")
    r = client.put(f"/api/v1/assignments/{assignment_id}/status", cookies=assignee,
                   json={"status": "completed"})
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert client.put(f"/api/v1/assignments/{assignment_id}", cookies=assignee,
                      json={"assignee_user_id": "u2"}).status_code == 403


def test_reassign_rejects_cross_tenant_assignee_before_write(client):
    seed = _seed_pack_tree(client, tenant="reassign-tenant")
    _seed_user("reassign-local", "reassign-tenant")
    _seed_user("reassign-foreign", "other-tenant")
    created = client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json={
        "pack_id": seed["pack"]["id"], "agent_id": seed["pack"]["agent_id"],
        "questions": [{"assignee_user_id": "reassign-local", "question": "Original"}],
    }).json()[0]

    r = client.put(f"/api/v1/assignments/{created['id']}", cookies=seed["admin"],
                   json={"assignee_user_id": "reassign-foreign"})
    assert r.status_code == 404
    current = client.get("/api/v1/assignments", params={"pack_id": seed["pack"]["id"]},
                         cookies=seed["admin"]).json()[0]
    assert current["assignee_user_id"] == "reassign-local"


def test_reassign_rejects_section_question_mutation_and_preserves_original(client):
    seed = _seed_pack_tree(client, tenant="reassign-section")
    _seed_user("section-user", "reassign-section")
    created = client.post("/api/v1/assignments/bulk", cookies=seed["admin"],
                          json=_section_assignment_payload(seed, assignee="section-user")).json()[0]

    r = client.put(f"/api/v1/assignments/{created['id']}", cookies=seed["admin"],
                   json={"question": "Mutated question"})
    assert r.status_code == 422
    current = client.get("/api/v1/assignments", params={"pack_id": seed["pack"]["id"]},
                         cookies=seed["admin"]).json()[0]
    assert current["question"] == "Trusted persisted question"


def test_delete_by_section_and_pack_via_api(client):
    seed = _seed_pack_tree(client, tenant="assignco4")
    _seed_user("u1", "assignco4")
    client.post("/api/v1/assignments/bulk", cookies=seed["admin"],
                json=_section_assignment_payload(seed, assignee="u1"))
    r = client.delete(
        f"/api/v1/assignments/section/{seed['pack']['id']}/{seed['leaf']['id']}",
        cookies=seed["admin"],
    )
    assert r.status_code == 200 and r.json()["deleted_count"] == 1
    assert client.delete(
        f"/api/v1/assignments/section/{seed['pack']['id']}/{seed['leaf']['id']}",
        cookies=seed["admin"],
    ).status_code == 404


def test_send_reminder_without_email_reports_failure(client):
    seed = _seed_pack_tree(client, tenant="assignco5")
    _seed_user("u1", "assignco5", email="")
    client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json={
        "pack_id": seed["pack"]["id"], "agent_id": "w1",
        "questions": [{"assignee_user_id": "u1", "question": "Q"}],
    })
    r = client.post("/api/v1/assignments/send-reminder", cookies=seed["admin"],
                    json={"pack_id": seed["pack"]["id"], "assignee_user_id": "u1"})
    assert r.status_code == 200
    assert r.json()["reminders_sent"] == 0


def test_send_reminder_uses_persisted_tenant_user_email(client, monkeypatch):
    seed = _seed_pack_tree(client, tenant="assignco6")
    _seed_user("u1", "assignco6", email="persisted@invalid")
    client.post("/api/v1/assignments/bulk", cookies=seed["admin"], json={
        "pack_id": seed["pack"]["id"], "agent_id": "w1",
        "questions": [{"assignee_user_id": "u1", "question": "Confidential"}],
    })
    sent = []
    monkeypatch.setattr(
        "app.modules.assignments.router.get_email_sender",
        lambda: type("Sender", (), {"send": lambda _self, **kwargs: sent.append(kwargs)})(),
    )
    response = client.post("/api/v1/assignments/send-reminder", cookies=seed["admin"], json={
        "pack_id": seed["pack"]["id"], "assignee_user_id": "u1",
        "assignee_email": "attacker@invalid",
    })
    assert response.status_code == 200
    assert sent[0]["to"] == "persisted@invalid"
    assert client.post(
        "/api/v1/assignments/send-reminder", cookies=seed["admin"],
        json={"pack_id": seed["pack"]["id"]},
    ).status_code == 422
