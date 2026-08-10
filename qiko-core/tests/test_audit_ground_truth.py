"""Verified ground truth: a human decision that permanently overrides the AI.

Two endpoints write an approved answer into the tenant's knowledge base as trusted ground truth, so
future answers are grounded in it instead of being generated afresh. The verified_answers table they
write into carries a created_at and nothing else: no actor, no agent_id. So when a worker starts giving
an answer nobody recognises, there was no way to find out who decided it was correct.
"""
import asyncio

from app.modules.agents.service import Agent
from app.modules.audit import registry
from tests.helpers import auth_cookies

C = auth_cookies("gtco", "owner", user_id="u-gt", email="reviewer@gtco.invalid")

APPROVED = "Our ISO 27001 certificate covers the whole delivery organisation, ACME Ltd included."


def _worker(client, worker_id: str = "a1") -> None:
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=worker_id, tenant="gtco", name="Bid Bot", status="ready")))


def _rows(client) -> list[dict]:
    return [r for r in client.app.state.audit.rows if r["action"] == registry.ANSWER_APPROVED]


def test_planting_ground_truth_records_who_decided(client):
    _worker(client)
    response = client.post("/api/v1/agents/feedback", cookies=C, json={
        "agent_id": "a1", "requirement_id": "R-14", "topic": "certifications",
        "approved_text": APPROVED})
    assert response.status_code == 200

    row = _rows(client)[0]
    assert row["actor_label"] == "reviewer@gtco.invalid"
    assert row["target_id"] == "R-14"
    assert row["target_label"] == "certifications"
    assert row["event_metadata"]["agent_id"] == "a1"
    assert row["tenant_id"] == "gtco"


def test_the_approved_text_is_never_copied_into_the_row(client):
    """It is customer content, it is already durable in the knowledge base, and copying it here would
    duplicate it into a store with a different retention window and a different erasure path. The
    question this row answers is who decided, not what they wrote."""
    _worker(client)
    client.post("/api/v1/agents/feedback", cookies=C, json={
        "agent_id": "a1", "requirement_id": "R-14", "topic": "certifications",
        "approved_text": APPROVED})

    row = _rows(client)[0]
    assert APPROVED not in str(row)
    assert "ACME Ltd" not in str(row)
    # The length is kept, because "approved 40 characters" and "approved 4,000" are different acts.
    assert row["changes"]["characters"]["to"] == len(APPROVED)


def test_the_tender_review_path_is_recorded_too(client):
    """Two endpoints write the same kind of ground truth. Auditing one and not the other would leave a
    trail that looks complete and is not."""
    _worker(client)
    pack = client.post("/api/v1/rfp/packs", cookies=C,
                       json={"title": "Framework", "agent_id": "a1"}).json()
    response = client.post(f"/api/v1/rfp/packs/{pack['id']}/feedback", cookies=C, json={
        "req_id": "R-2", "decision": "Approve", "comment": APPROVED})
    assert response.status_code == 200

    row = _rows(client)[0]
    assert row["event_metadata"]["source"] == "tender_review"
    assert row["event_metadata"]["wrote_ground_truth"] is True
    assert APPROVED not in str(row)


def test_a_rejection_is_recorded_although_it_touches_no_knowledge_base(client):
    """A review where somebody said no is as much a decision as one where they said yes, and an audit
    holding only the approvals cannot show that a draft was looked at and turned down."""
    _worker(client)
    pack = client.post("/api/v1/rfp/packs", cookies=C,
                       json={"title": "Framework", "agent_id": "a1"}).json()
    client.post(f"/api/v1/rfp/packs/{pack['id']}/feedback", cookies=C, json={
        "req_id": "R-3", "decision": "Reject", "comment": "not our scope"})

    row = _rows(client)[0]
    assert row["changes"]["decision"]["to"] == "reject"
    assert row["event_metadata"]["wrote_ground_truth"] is False


def test_an_approve_with_nothing_in_it_is_not_ground_truth(client):
    """An Approve with an empty comment writes nothing to the knowledge base, so it did not create
    ground truth however the UI labelled it. The row has to reflect what happened, not what was
    clicked."""
    _worker(client)
    pack = client.post("/api/v1/rfp/packs", cookies=C,
                       json={"title": "Framework", "agent_id": "a1"}).json()
    client.post(f"/api/v1/rfp/packs/{pack['id']}/feedback", cookies=C, json={
        "req_id": "R-4", "decision": "Approve", "comment": "   "})

    row = _rows(client)[0]
    assert row["changes"]["decision"]["to"] == "approve"
    assert row["event_metadata"]["wrote_ground_truth"] is False


def test_a_viewer_cannot_plant_ground_truth(client):
    """The endpoint's own docstring says a viewer must not be able to plant verified ground truth that
    every future answer gets grounded against. Worth an assertion rather than a comment."""
    _worker(client)
    viewer = auth_cookies("gtco", "viewer", user_id="u-view", email="viewer@gtco.invalid")
    assert client.post("/api/v1/agents/feedback", cookies=viewer, json={
        "agent_id": "a1", "requirement_id": "R-9", "topic": "t",
        "approved_text": "planted"}).status_code == 403
    assert _rows(client) == []


def test_the_table_it_writes_into_still_cannot_attribute_on_its_own():
    """Named rather than left implied: verified_answers has no actor and no agent_id, so this audit row
    is the only attribution that exists. Adding those columns is a migration and a separate change; what
    matters here is that the gap is closed somewhere rather than nowhere."""
    from app.db.models import VerifiedAnswer

    columns = {c.name for c in VerifiedAnswer.__table__.columns}
    assert "created_at" in columns
    assert not columns & {"created_by", "created_by_email", "actor_id", "agent_id"}, (
        "if the table gains attribution, this test and the comments around it should be revisited")
