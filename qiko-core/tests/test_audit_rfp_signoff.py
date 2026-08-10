"""Tender governance: the closest thing this platform has to a signature on a document.

A pack could be locked, reopened, finalised and marked won with no trace of who decided any of it. For a
document a customer submits to a public body, that was the gap that mattered most in this module.
"""
import asyncio

from app.modules.agents.service import Agent
from app.modules.audit import registry
from tests.helpers import auth_cookies

C = auth_cookies("bidco", "owner", user_id="u-bid", email="lead@bidco.invalid")


def _pack(client) -> str:
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="a1", tenant="bidco", name="Bid Bot", status="ready")))
    created = client.post("/api/v1/rfp/packs", cookies=C,
                          json={"title": "Council framework", "agent_id": "a1"}).json()
    return created["id"]


def _section_with_questions(client, pack_id: str, count: int = 3) -> tuple[str, list[str]]:
    section = client.post(f"/api/v1/rfp/packs/{pack_id}/sections", cookies=C,
                          json={"code": "3.1", "name": "Method statement"}).json()
    section_id = section["id"]
    questions = []
    for index in range(count):
        created = client.post(f"/api/v1/rfp/packs/{pack_id}/sections/{section_id}/questions",
                              cookies=C, json={"text": f"Question {index}"}).json()
        questions.append(created["id"])
    return section_id, questions


def _rows(client, action: str) -> list[dict]:
    return [r for r in client.app.state.audit.rows if r["action"] == action]


def test_locking_an_answer_is_recorded_as_a_sign_off(client):
    pack_id = _pack(client)
    _section, questions = _section_with_questions(client, pack_id, 1)
    response = client.post(
        f"/api/v1/rfp/packs/{pack_id}/questions/{questions[0]}/lock", cookies=C)
    assert response.status_code == 200

    row = _rows(client, registry.ANSWER_LOCKED)[0]
    assert row["target_id"] == questions[0]
    assert row["target_label"] == pack_id
    assert row["actor_label"] == "lead@bidco.invalid"
    assert row["changes"]["locked"] == {"from": False, "to": True}


def test_re_locking_is_not_a_second_sign_off(client):
    """A stream of them would bury the real ones, and the second click did not approve anything new."""
    pack_id = _pack(client)
    _section, questions = _section_with_questions(client, pack_id, 1)
    for _ in range(3):
        client.post(f"/api/v1/rfp/packs/{pack_id}/questions/{questions[0]}/lock", cookies=C)
    assert len(_rows(client, registry.ANSWER_LOCKED)) == 1


def test_reopening_is_its_own_action_not_a_lock_with_a_false(client):
    """Reversing an approval after review is the move a bid team would be asked about afterwards, and it
    should be findable without reading the diff of every lock event."""
    pack_id = _pack(client)
    _section, questions = _section_with_questions(client, pack_id, 1)
    client.post(f"/api/v1/rfp/packs/{pack_id}/questions/{questions[0]}/lock", cookies=C)
    client.post(f"/api/v1/rfp/packs/{pack_id}/questions/{questions[0]}/unlock", cookies=C)

    assert len(_rows(client, registry.ANSWER_UNLOCKED)) == 1
    assert _rows(client, registry.ANSWER_UNLOCKED)[0]["changes"]["locked"] == {
        "from": True, "to": False}
    # Filterable on its own, which is the point of separating it.
    trail = client.app.state.audit.rows
    assert {r["action"] for r in trail} >= {registry.ANSWER_LOCKED, registry.ANSWER_UNLOCKED}


def test_unlocking_something_already_open_records_nothing(client):
    pack_id = _pack(client)
    _section, questions = _section_with_questions(client, pack_id, 1)
    client.post(f"/api/v1/rfp/packs/{pack_id}/questions/{questions[0]}/unlock", cookies=C)
    assert _rows(client, registry.ANSWER_UNLOCKED) == []


def test_a_bulk_lock_records_how_many_answers_it_signed_off(client):
    """Counted before the operation, because afterwards every one is locked and the number would always
    equal the section size regardless of what the click actually did."""
    pack_id = _pack(client)
    section_id, questions = _section_with_questions(client, pack_id, 3)
    # One already locked, so the bulk click signs off two.
    client.post(f"/api/v1/rfp/packs/{pack_id}/questions/{questions[0]}/lock", cookies=C)
    response = client.post(
        f"/api/v1/rfp/packs/{pack_id}/sections/{section_id}/lock-all", cookies=C)
    assert response.status_code == 200

    row = _rows(client, registry.SECTION_LOCKED)[0]
    assert row["changes"]["questions_locked"]["to"] == 2, "not the section size"
    assert row["target_id"] == section_id


def test_a_bulk_lock_over_an_already_locked_section_records_nothing(client):
    pack_id = _pack(client)
    section_id, _questions = _section_with_questions(client, pack_id, 2)
    client.post(f"/api/v1/rfp/packs/{pack_id}/sections/{section_id}/lock-all", cookies=C)
    client.post(f"/api/v1/rfp/packs/{pack_id}/sections/{section_id}/lock-all", cookies=C)
    assert len(_rows(client, registry.SECTION_LOCKED)) == 1


def test_finalising_records_that_it_was_the_submission_point(client):
    """Reaching "final" is the roll-up of every section lock: the moment the pack stopped being a draft.
    Months later, "was review complete when this was finalised" has to be answerable from the audit
    rather than from the pack's current state, which by then has moved on."""
    pack_id = _pack(client)
    section_id, _questions = _section_with_questions(client, pack_id, 2)
    client.post(f"/api/v1/rfp/packs/{pack_id}/sections/{section_id}/lock-all", cookies=C)
    response = client.put(f"/api/v1/rfp/packs/{pack_id}/stage", cookies=C, json={"stage": "final"})
    assert response.status_code == 200

    row = _rows(client, registry.PACK_STAGE_CHANGED)[-1]
    assert row["changes"]["stage"]["to"] == "final"
    assert row["event_metadata"]["finalised"] is True
    assert row["event_metadata"]["title"] == "Council framework"


def test_a_refused_finalise_leaves_no_row(client):
    """The guard exists so the generic stage transition cannot skip review sign-off. A refusal is not a
    change, so it must not leave a row claiming one."""
    pack_id = _pack(client)
    _section_with_questions(client, pack_id, 2)  # nothing locked
    assert client.put(f"/api/v1/rfp/packs/{pack_id}/stage", cookies=C,
                      json={"stage": "final"}).status_code == 409
    assert not [r for r in _rows(client, registry.PACK_STAGE_CHANGED)
                if r["changes"].get("stage", {}).get("to") == "final"]


def test_a_stage_set_to_its_current_value_records_nothing(client):
    pack_id = _pack(client)
    before = len(_rows(client, registry.PACK_STAGE_CHANGED))
    stage = client.get(f"/api/v1/rfp/packs/{pack_id}", cookies=C).json().get("stage")
    if stage:
        client.put(f"/api/v1/rfp/packs/{pack_id}/stage", cookies=C, json={"stage": stage})
        assert len(_rows(client, registry.PACK_STAGE_CHANGED)) == before


def test_the_outcome_is_recorded_because_a_win_rate_has_to_be_defensible(client):
    """It feeds /rfp/packs/stats, so its integrity is commercial rather than merely operational: a win
    rate nobody can attribute is a number a bid team reports and cannot defend."""
    pack_id = _pack(client)
    response = client.put(f"/api/v1/rfp/packs/{pack_id}/outcome", cookies=C,
                          json={"outcome": "won", "value": 250000})
    assert response.status_code == 200

    row = _rows(client, registry.PACK_OUTCOME_RECORDED)[0]
    assert row["changes"]["outcome"]["to"] == "won"
    assert row["changes"]["value"]["to"] == 250000
    assert row["actor_label"] == "lead@bidco.invalid"


def test_every_governance_action_carries_the_pack_it_belongs_to(client):
    """A locked answer id means nothing on its own: the question an operator asks is about the bid."""
    pack_id = _pack(client)
    section_id, questions = _section_with_questions(client, pack_id, 2)
    client.post(f"/api/v1/rfp/packs/{pack_id}/questions/{questions[0]}/lock", cookies=C)
    client.post(f"/api/v1/rfp/packs/{pack_id}/sections/{section_id}/lock-all", cookies=C)
    client.put(f"/api/v1/rfp/packs/{pack_id}/outcome", cookies=C, json={"outcome": "lost"})

    governance = [r for r in client.app.state.audit.rows
                  if r["action"].startswith("data.answer_") or r["action"].startswith("data.section_")
                  or r["action"].startswith("data.pack_")]
    assert governance
    for row in governance:
        assert row["event_metadata"]["pack_id"] == pack_id
        assert row["tenant_id"] == "bidco"


def test_the_previous_state_is_captured_before_the_mutation_not_after():
    """This is the second time this exact bug has landed in this programme.

    The stores return LIVE rows, so reading `existing.locked` after `lock_question` has run reads the
    value the mutation just wrote: every lock looked like a re-lock and no row was written at all. The
    credential audit in wave 2 failed the same way, for the same reason, and both failures are silent,
    which is what makes them worth pinning rather than just fixing.

    Asserted against the source because the behavioural tests above only catch it when the in-memory
    store happens to alias; a SQL store that returned a detached copy would hide it again.
    """
    import inspect

    from app.modules.rfp import router

    for handler in (router.lock_question, router.unlock_question):
        source = inspect.getsource(handler)
        assert "was_locked = bool(getattr(existing" in source, f"{handler.__name__} must snapshot"
        assert source.index("was_locked =") < source.index("await tree.lock_question("), (
            f"{handler.__name__} reads the flag after the mutation")
        # Everything after the mutation must not read the live row again. Sliced from the mutation
        # rather than from the assignment, because the assignment line legitimately contains the read.
        after_mutation = source[source.index("await tree.lock_question("):]
        assert "existing." not in after_mutation and "getattr(existing" not in after_mutation, (
            f"{handler.__name__} must not re-read the live row after mutating it")

    stage = inspect.getsource(router.set_stage)
    assert stage.index('previous = getattr(pack, "stage"') < stage.index("await svc.set_stage(")

    outcome = inspect.getsource(router.set_outcome)
    assert outcome.index("previous_outcome = getattr(persisted") < outcome.index(
        "await svc.set_outcome_for_enabled_agent(")
