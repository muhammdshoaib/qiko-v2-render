import pytest

from app.modules.assignments.service import (
    AssignmentError,
    AssignmentService,
    QuestionAssignBody,
    SectionAssignBody,
)

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
def test_assignments_api_bulk_and_dashboard(client):
    admin = auth_cookies("assignco", "owner", user_id="admin-1")
    r = client.post("/api/v1/assignments/bulk", cookies=admin, json={
        "pack_id": "pack1", "agent_id": "w1", "rfp_title": "Tender X",
        "sections": [{"section_id": "B1", "assignee_user_id": "u1", "questions": ["Q1", "Q2"],
                     "title": "Org Structure"}],
        "questions": [{"assignee_user_id": "u2", "question": "Standalone"}],
    })
    assert r.status_code == 200 and len(r.json()) == 3

    listed = client.get("/api/v1/assignments", params={"pack_id": "pack1"}, cookies=admin).json()
    assert len(listed) == 3

    dash = client.get("/api/v1/assignments/dashboard",
                      params={"pack_id": "pack1", "member_user_ids": "u1,u2"}, cookies=admin).json()
    u1 = next(r for r in dash if r["user_id"] == "u1")
    assert u1["assigned"] == 2


def test_assignments_bulk_requires_admin_role(client):
    viewer = auth_cookies("assignco2", "viewer")
    r = client.post("/api/v1/assignments/bulk", cookies=viewer,
                    json={"pack_id": "p", "agent_id": "w1", "questions": [{"assignee_user_id": "x", "question": "Q"}]})
    assert r.status_code == 403


def test_assignee_can_update_own_status_but_not_reassign(client):
    admin = auth_cookies("assignco3", "owner", user_id="admin-1")
    created = client.post("/api/v1/assignments/bulk", cookies=admin, json={
        "pack_id": "p1", "agent_id": "w1",
        "questions": [{"assignee_user_id": "u1", "question": "Q"}],
    }).json()
    assignment_id = created[0]["id"]

    # a different, non-owning user (viewer role, not the assignee) is rejected
    other = auth_cookies("assignco3", "viewer", user_id="other-user")
    assert client.put(f"/api/v1/assignments/{assignment_id}/status", cookies=other,
                      json={"status": "completed"}).status_code == 403

    # the actual assignee (u1) can mark their own item completed
    assignee = auth_cookies("assignco3", "viewer", user_id="u1")
    r = client.put(f"/api/v1/assignments/{assignment_id}/status", cookies=assignee,
                   json={"status": "completed"})
    assert r.status_code == 200 and r.json()["status"] == "completed"

    # but only owner/admin can reassign
    assert client.put(f"/api/v1/assignments/{assignment_id}", cookies=assignee,
                      json={"assignee_user_id": "u2"}).status_code == 403


def test_delete_by_section_and_pack_via_api(client):
    admin = auth_cookies("assignco4", "owner")
    client.post("/api/v1/assignments/bulk", cookies=admin, json={
        "pack_id": "p2", "agent_id": "w1",
        "sections": [{"section_id": "S1", "assignee_user_id": "u1", "questions": ["Q1"]}],
    })
    r = client.delete("/api/v1/assignments/section/p2/S1", cookies=admin)
    assert r.status_code == 200 and r.json()["deleted_count"] == 1
    assert client.delete("/api/v1/assignments/section/p2/S1", cookies=admin).status_code == 404


def test_send_reminder_without_email_reports_failure(client):
    admin = auth_cookies("assignco5", "owner")
    client.post("/api/v1/assignments/bulk", cookies=admin, json={
        "pack_id": "p3", "agent_id": "w1",
        "questions": [{"assignee_user_id": "u1", "question": "Q"}],
    })
    r = client.post("/api/v1/assignments/send-reminder", cookies=admin,
                    json={"pack_id": "p3", "assignee_user_id": "u1"})
    assert r.status_code == 200
    assert r.json()["reminders_sent"] == 0
