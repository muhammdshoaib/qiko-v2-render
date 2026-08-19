"""Functional API tests via TestClient: routers are authenticated, tenant-scoped (from token), RBAC-gated."""
import pytest

from app.modules.ai.gateway import LLMResponse
from tests.helpers import auth_cookies, bootstrap_admin

def _cookies():
    return auth_cookies("acme", "owner")
ISO = "IDG holds a current ISO 9001 certification valid through 2027."


@pytest.fixture(autouse=True)
def _non_stub_provider(monkeypatch):
    class Provider:
        def generate(self, prompt, **_kwargs):
            return LLMResponse(text=prompt, model="test", stub=False)

    monkeypatch.setattr("app.modules.agentcore.generator.get_provider", lambda: Provider())


def test_unauthenticated_is_401(client):
    assert client.post("/api/v1/knowledge/search", json={"query": "x"}).status_code == 401


def test_tenant_comes_from_token_not_header(client):
    # even if a caller spoofs a header, the tenant is the token's; ingest under token tenant (acme)
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO},
                headers={"X-Tenant-Id": "attacker"}, cookies=_cookies())
    hits = client.post("/api/v1/knowledge/search", json={"query": "ISO 9001"},
                       headers={"X-Tenant-Id": "attacker"}, cookies=_cookies()).json()["results"]
    assert any("ISO 9001" in h for h in hits)
    # a token for a different tenant sees nothing
    other = client.post("/api/v1/knowledge/search", json={"query": "ISO 9001"},
                        cookies=auth_cookies("beta")).json()["results"]
    assert other == []


def test_knowledge_ingest_list_delete(client):
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=_cookies())
    assert client.get("/api/v1/knowledge/documents", cookies=_cookies()).json()[0]["doc_id"] == "iso"
    assert client.delete("/api/v1/knowledge/documents/iso", cookies=_cookies()).json()["removed"] >= 1


def test_knowledge_mutations_require_editor_role(client):
    # A viewer must not be able to inject or delete knowledge-base content (RAG data poisoning /
    # destruction) -- writes need Editor-or-above, mirroring rfp. Reads stay open to a viewer.
    viewer = auth_cookies("kbrbac", "viewer")
    editor = auth_cookies("kbrbac", "editor")
    assert client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO},
                       cookies=viewer).status_code == 403
    assert client.post("/api/v1/knowledge/ingest-file", data={"doc_id": "iso"},
                       files={"file": ("iso.txt", ISO, "text/plain")}, cookies=viewer).status_code == 403
    assert client.delete("/api/v1/knowledge/documents/iso", cookies=viewer).status_code == 403
    # an editor can ingest, read, and delete
    assert client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO},
                       cookies=editor).status_code == 200
    assert client.post("/api/v1/knowledge/search", json={"query": "ISO 9001"}, cookies=viewer).status_code == 200
    assert client.delete("/api/v1/knowledge/documents/iso", cookies=editor).status_code == 200


def test_knowledge_ingest_text_has_max_length(client):
    # An oversized free-text ingest is rejected by validation before it hits chunk -> embed.
    too_big = "x" * (2 * 1024 * 1024 + 1)
    r = client.post("/api/v1/knowledge/ingest", json={"doc_id": "big", "text": too_big}, cookies=_cookies())
    assert r.status_code == 422


def test_knowledge_ingest_file_enforces_upload_cap(client, monkeypatch):
    # A file larger than the per-endpoint cap is refused with 413 (shrink the cap so the test
    # payload stays small and never trips the global request-size middleware first).
    monkeypatch.setattr("app.modules.knowledge.router.MAX_UPLOAD_BYTES", 16)
    r = client.post("/api/v1/knowledge/ingest-file", data={"doc_id": "big"},
                    files={"file": ("big.txt", b"x" * 64, "text/plain")}, cookies=_cookies())
    assert r.status_code == 413


def test_agents_lifecycle_and_plan_gate(client):
    c = auth_cookies("agteam", "owner")
    created = client.post("/api/v1/agents", json={"name": "IDG", "plan": "free"}, cookies=c).json()
    assert created["status"] == "training"
    assert client.post(f"/api/v1/agents/{created['id']}/ready", cookies=c).json()["status"] == "ready"
    assert client.post("/api/v1/agents", json={"name": "second", "plan": "free"}, cookies=c).status_code == 403


def test_agent_plan_limit_cannot_be_bypassed_by_client_supplied_plan(client):
    """Regression: /agents used to trust a client-supplied "plan" field to decide the worker
    limit, so any free-tier tenant could self-upgrade past it by just sending a different plan
    name. The plan must always come from the tenant's real (server-side) subscription."""
    c = auth_cookies("bypassteam", "owner")
    assert client.post("/api/v1/agents", json={"name": "first"}, cookies=c).status_code == 200
    for fake_plan in ("pro", "enterprise"):
        r = client.post("/api/v1/agents", json={"name": "second", "plan": fake_plan}, cookies=c)
        assert r.status_code == 403, f"plan={fake_plan} should not bypass the free-tier limit"


def test_premium_plan_worker_limit_blocks_fourth_worker(client):
    """A Premium (pro) subscription allows exactly 3 workers; the fourth POST /agents is 403."""
    c = auth_cookies("premiumteam", "owner")
    assert client.post("/api/v1/billing/subscription/activate", json={"plan": "pro"}, cookies=c).status_code == 200
    for i in range(3):
        r = client.post("/api/v1/agents", json={"name": f"worker-{i}"}, cookies=c)
        assert r.status_code == 200, r.text
    r = client.post("/api/v1/agents", json={"name": "worker-3"}, cookies=c)
    assert r.status_code == 403, r.text


def test_batch_answer_is_grounded_confidence_scored_and_gated(client):
    c = auth_cookies("batchco", "owner")
    agent_id = client.post("/api/v1/agents", json={"name": "Batch"}, cookies=c).json()["id"]
    client.post("/api/v1/knowledge/ingest", json={"doc_id": "iso", "text": ISO}, cookies=c)
    r = client.post("/api/v1/agents/batch-answer",
                     json={"questions": ["Does IDG hold ISO 9001?", "What is the capital of Mars?"],
                           "agent_id": agent_id},
                     cookies=c)
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 2
    for item in results:
        assert set(item) >= {"id", "question", "answer", "confidence", "decision", "citations"}
        assert item["decision"] in ("auto_accept", "human_review")
        assert 0.0 <= item["confidence"] <= 1.0


def test_feedback_approves_answer_into_flywheel(client):
    c = auth_cookies("feedbackco", "owner")
    agent_id = client.post("/api/v1/agents", json={"name": "Feedback"}, cookies=c).json()["id"]
    r = client.post("/api/v1/agents/feedback",
                     json={"requirement_id": "q1", "topic": "iso",
                           "approved_text": "IDG holds ISO 9001.", "agent_id": agent_id},
                     cookies=c)
    assert r.status_code == 200 and r.json() == {"verified": True}
    # the next answer on the same topic should be grounded in the verified text, not escalate
    r2 = client.post("/api/v1/agents/batch-answer", json={"questions": ["Does the company hold ISO 9001?"], "agent_id": agent_id}, cookies=c)
    assert r2.status_code == 200


def test_feedback_requires_editor_role(client):
    # Same knowledge-base write as the rfp-pack feedback endpoint -- a viewer must not be able
    # to plant "verified ground truth" for the whole tenant.
    c = auth_cookies("feedbackco2", "viewer")
    r = client.post("/api/v1/agents/feedback",
                     json={"requirement_id": "q1", "topic": "iso", "approved_text": "should be blocked"},
                     cookies=c)
    assert r.status_code == 403


def test_batch_export_returns_xlsx(client):
    c = auth_cookies("exportco", "owner")
    agent_id = client.post("/api/v1/agents", json={"name": "Export"}, cookies=c).json()["id"]
    r = client.post(
        "/api/v1/agents/batch-export",
        json={"questions": ["Any question?"], "agent_id": agent_id}, cookies=c)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(r.content) > 0


def test_batch_answer_requires_editor_role(client):
    # A read-only viewer must not be able to run bulk LLM generation (up to 200 calls per request).
    c = auth_cookies("batchviewer", "viewer")
    r = client.post("/api/v1/agents/batch-answer", json={"questions": ["Does IDG hold ISO 9001?"]}, cookies=c)
    assert r.status_code == 403


def test_batch_export_requires_editor_role(client):
    c = auth_cookies("batchviewer2", "viewer")
    r = client.post("/api/v1/agents/batch-export", json={"questions": ["Any question?"]}, cookies=c)
    assert r.status_code == 403


def test_agents_write_requires_editor_role(client):
    # a viewer cannot create agents
    r = client.post("/api/v1/agents", json={"name": "x"}, cookies=auth_cookies("t", "viewer"))
    assert r.status_code == 403


def test_admin_requires_platform_admin_not_tenant_role(client):
    """Regression: the tenant role (even "owner"/"admin" of your OWN tenant) must never grant
    cross-tenant platform-admin access -- every signed-up user is "owner" of their own tenant."""
    subs = [{"customer_id": "c1", "plan": "pro", "price_cents": 5000}]
    assert client.post("/api/v1/admin/revenue", json=subs, cookies=auth_cookies("t", "editor")).status_code == 403
    assert client.post("/api/v1/admin/revenue", json=subs, cookies=auth_cookies("t", "owner")).status_code == 403
    assert client.post("/api/v1/admin/revenue", json=subs, cookies=auth_cookies("t", "admin")).status_code == 403

    admin_email = "platform-admin@invalid"
    bootstrap_admin(client, admin_email)
    ok = client.post("/api/v1/admin/revenue", json=subs, cookies=auth_cookies("t", "viewer", email=admin_email))
    assert ok.json()["active_subscriptions"] == 1
