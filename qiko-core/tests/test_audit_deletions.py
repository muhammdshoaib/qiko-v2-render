"""Wave 4 of audit coverage: destruction of customer data.

Five endpoints destroy data a customer would dispute losing, and none recorded anything. What matters
in each case is not that a deletion happened but HOW MUCH was destroyed: "a document was deleted" is a
fact nobody argues about, while "3,412 passages were removed from the corpus" is the row that explains
why answers got worse on a particular day.
"""
import asyncio

from app.modules.agents.service import Agent
from app.modules.audit import registry
from tests.helpers import auth_cookies

C = auth_cookies("delco", "owner", user_id="u-del", email="owner@delco.invalid")


def _worker(client, worker_id: str = "a1") -> None:
    """A ready, enabled worker: both the chat and tender endpoints refuse to act without one."""
    asyncio.run(client.app.state.agents.store.add(
        Agent(id=worker_id, tenant="delco", name="Bid Bot", status="ready")))


def _events(client, action: str) -> list[dict]:
    return [r for r in client.app.state.audit.rows if r["action"] == action]


def test_deleting_a_document_records_how_much_of_the_corpus_went_with_it(client):
    """Not recoverable from within the product: the source file is not retained, so the only remedy is
    for the customer to find and re-upload it."""
    client.post("/api/v1/knowledge/ingest", cookies=C,
                json={"doc_id": "d1", "text": "one. two. three. " * 40})
    response = client.delete("/api/v1/knowledge/documents/d1?reason=superseded", cookies=C)
    assert response.status_code == 200
    removed = response.json()["removed"]
    assert removed > 0

    row = _events(client, registry.DOCUMENT_DELETED)[0]
    assert row["changes"]["passages_removed"]["to"] == removed
    assert row["changes"]["doc_id"]["to"] == "d1"
    assert row["reason"] == "superseded"
    assert row["actor_label"] == "owner@delco.invalid"


def test_clearing_a_conversation_records_the_message_count_before_the_wipe(client):
    """Reachable by any authenticated role including viewer, with no confirmation. Counting afterwards
    would always report zero, which is the shape of a record that looks present and says nothing."""
    _worker(client)
    client.post("/api/v1/chat/ask", cookies=C,
                json={"agent_id": "a1", "user_id": "u-del", "question": "hello?"})
    conversation = client.post("/api/v1/chat/conversations", cookies=C,
                               json={"user_id": "u-del", "agent_id": "a1"}).json()
    cid = conversation.get("conversation_id") or conversation.get("id")

    client.delete(f"/api/v1/chat/history/{cid}", cookies=C)
    rows = _events(client, registry.CHAT_HISTORY_DELETED)
    assert rows, "clearing a conversation must leave a record"
    assert rows[0]["changes"]["messages_removed"]["to"] >= 0
    assert rows[0]["target_id"] == cid


def test_the_count_is_taken_before_the_deletion_not_after(client):
    """The ordering is the whole substance of these rows."""
    from pathlib import Path

    modules = Path(__file__).resolve().parents[1] / "app" / "modules"
    chat = (modules / "chat" / "router.py").read_text()
    body = chat[chat.index("async def clear_history"):chat.index("class ConversationBody")]
    assert body.index("await chat.history(") < body.index("await chat.clear(")

    rfp = (modules / "rfp" / "router.py").read_text()
    pack_body = rfp[rfp.index("async def delete_pack"):rfp.index("async def _start_generation")]
    assert pack_body.index("counts = {") < pack_body.index("await answers.delete_for_pack")


def test_deleting_a_tender_pack_records_what_it_cascaded(client):
    """Weeks of a bid team's work across four tables, removed with no undo. The list of what cascaded
    is what tells a support conversation whether the answers are gone too."""
    _worker(client)
    pack = client.post("/api/v1/rfp/packs", cookies=C,
                       json={"title": "Council framework", "agent_id": "a1"}).json()
    pack_id = pack.get("id") or pack.get("pack_id")
    response = client.delete(f"/api/v1/rfp/packs/{pack_id}?reason=duplicate", cookies=C)
    assert response.status_code == 200

    row = _events(client, registry.RFP_PACK_DELETED)[0]
    assert row["target_id"] == pack_id
    assert "answers" in row["event_metadata"]["cascaded"]
    assert "questions" in row["event_metadata"]["cascaded"]
    assert row["reason"] == "duplicate"


def test_financial_file_deletion_records_ids_not_filenames(client):
    """A filename can carry a client name. The id is what identifies the record for a restore, and it
    is not personal data."""
    from pathlib import Path

    finance = (Path(__file__).resolve().parents[1] / "app" / "modules" / "finance" /
               "router.py").read_text()
    body = finance[finance.index("async def delete_files"):]
    assert '"file_ids": ids[:50]' in body, "record the ids"
    assert "filename" not in body.split("audit.record")[1][:400], "and not the filenames"


def test_every_deletion_action_is_transactional_in_the_registry():
    """These are the events a customer disputes, so losing the row is not an acceptable outcome."""
    for action in (registry.DOCUMENT_DELETED, registry.RFP_PACK_DELETED,
                   registry.FINANCE_FILES_DELETED, registry.CHAT_HISTORY_DELETED):
        assert registry.spec_for(action).durability == registry.CRITICAL


def test_a_deletion_row_survives_without_the_thing_it_describes():
    """The table carries no foreign keys precisely so that the history of a deletion is not deleted
    along with its subject."""
    from app.db.models import AuditEventRow

    assert not [c for c in AuditEventRow.__table__.columns if c.foreign_keys], (
        "a foreign key would either block the deletion or cascade away its own record")
