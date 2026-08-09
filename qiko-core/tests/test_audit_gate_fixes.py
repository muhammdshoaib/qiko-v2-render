"""The findings from the security review of waves 1 to 5, each with a test.

The review ran after those waves had already merged and deployed to preprod, so every one of these was
a live defect rather than a pre-merge one. That is the cost of skipping the gate, and it is the reason
these are pinned rather than just fixed.
"""
import asyncio


from app.modules.audit import registry
from app.modules.audit.service import MAX_IDENTITY_CHARS, AuditEvent, build_row
from tests.helpers import auth_cookies


def test_an_oversized_identifier_cannot_suppress_its_own_row():
    """The worst finding of the review. target_id, target_label and the actor fields were the only
    strings build_row did not cap, and the columns are 320 chars. A 400-character email on a failed
    login made the INSERT raise, record() swallowed it by design, and the caller still got a clean 401.

    The one row an attacker cares about was the one they could switch off with whitespace.
    """
    padded = "a" * 400 + "@evil.invalid"
    row = build_row(AuditEvent(action=registry.LOGIN_FAILED, target_id=padded, target_label=padded,
                               actor_id=padded, actor_label=padded))
    for field in ("target_id", "target_label", "actor_id", "actor_label"):
        assert len(row[field]) <= MAX_IDENTITY_CHARS, f"{field} would overflow its column"


def test_a_padded_login_still_produces_a_row(client):
    asyncio.run(client.app.state.audit.rows.clear() or asyncio.sleep(0))
    response = client.post("/api/v1/auth/login",
                           json={"email": "b" * 500 + "@evil.invalid", "password": "x"})
    assert response.status_code == 401
    assert any(r["action"] == registry.LOGIN_FAILED for r in client.app.state.audit.rows), (
        "a padded address must not buy silence")


def test_no_action_claims_a_durability_its_call_sites_do_not_provide():
    """Ten actions were declared CRITICAL and written through the losable path. Two live consequences:
    the rows could vanish for exactly the events that must not vanish, and every routine deletion
    emitted an ERROR that Sentry turned into an alert, drowning the real "audit write failed" that
    shares the same logger.

    The old test asserted the declaration. This one is enforced by
    test_every_critical_action_with_a_call_site_has_a_transactional_one, which walks the source; here we
    only pin that the downgrade actually happened rather than being papered over.
    """
    for action in (registry.TENANT_ROLE_CHANGED, registry.TENANT_MEMBER_REMOVED,
                   registry.DOCUMENT_DELETED, registry.CHAT_HISTORY_DELETED,
                   registry.MFA_ENROLLED, registry.PASSWORD_CHANGED,
                   registry.PAYMENT_LINK_MARKED_PAID, registry.CUSTOMER_SOFT_DELETED,
                   registry.COST_CAP_SET):
        assert registry.spec_for(action).durability == registry.STANDARD


def test_the_synchronous_writer_carries_the_same_guard_as_the_async_one():
    """record_sync had no is_critical check, so the one money row the registry singles out was on the
    weak path with nothing pointing that out."""
    import inspect

    from app.modules.audit import service

    assert "is_critical(event.action)" in inspect.getsource(service.record_sync)


def test_clearing_a_conversation_counts_what_was_actually_deleted(client):
    """messages_removed came from chat.history(), which defaults to a 20-message window and has no SQL
    LIMIT. So it saturated at 20, and it materialised every message body to produce a number it then
    capped. Both halves of the docstring's claim were false."""
    import inspect

    from app.modules.chat import router as chat_router

    source = inspect.getsource(chat_router.clear_history)
    assert "await chat.clear(" in source
    assert "chat.history(" not in source, "counting by reading the window is what capped it at 20"

    store = client.app.state.chat.store
    asyncio.run(store.append("countco", "c1", "user", "one"))
    asyncio.run(store.append("countco", "c1", "assistant", "two"))
    asyncio.run(store.append("countco", "c1", "user", "three"))
    assert asyncio.run(client.app.state.chat.clear("countco", "c1")) == 3


def test_the_tender_pack_count_is_not_a_fabricated_zero():
    """It called tree.sections_for_pack behind a hasattr guard. No such method exists, so the guard was
    always false and every row in preprod recorded sections: 0. A fabricated zero is worse than an
    absent field, because it reads as evidence that nothing was there."""
    import inspect

    from app.modules.rfp import router as rfp_router

    source = inspect.getsource(rfp_router.delete_pack)
    # Comments stripped first: the comment explaining the fix names the method that never existed, so a
    # plain substring search fails on its own explanation. This is the third time in this programme a
    # source-reading test has done that.
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    assert "sections_for_pack" not in code, "that method never existed"
    assert "hasattr(tree" not in code, "a hasattr guard on a method that is absent is a silent zero"
    assert "await tree.sections.list(" in code
    assert "await tree.questions.list(" in code


def test_a_credential_test_row_means_a_credential_was_actually_used(client):
    """The call sat before the "is a credential configured" guard, so any editor could emit the signal
    on a worker with no credential at all. The docstring claims it is the cheapest indication that a
    leaked encryption key is being exercised; a row anyone can emit without a key is not that."""
    from app.modules.agents.service import Agent

    cookies = auth_cookies("credtest", "owner")
    asyncio.run(client.app.state.agents.store.add(
        Agent(id="w1", tenant="credtest", name="Bare Bot")))

    response = client.post("/api/v1/agents/w1/slack-credentials/test", cookies=cookies)
    assert response.status_code == 422, "no credential configured"
    assert not [r for r in client.app.state.audit.rows
                if r["action"] == registry.CREDENTIAL_TESTED], (
        "nothing was decrypted, so nothing should claim it was")


def test_a_key_rotation_does_not_report_every_re_save_as_a_rotation(monkeypatch):
    """_plaintext_of_config returns None on any decrypt failure, so after an ENCRYPTION_KEY rotation an
    unreadable previous value looked identical to no previous value, and rotated came out True even
    when the operator re-saved the same secret. Backwards from the field's purpose."""
    from app.modules.audit.credentials import credential_audit

    build = credential_audit(
        action=registry.CREDENTIAL_SET, provider="slack", tenant="t", agent_id="w1",
        agent_name="w1", claims={"sub": "u", "email": "u@t.invalid"}, secret="same-value",
        decrypt_previous=lambda _cfg: None)
    row = build({"slack_bot_token_encrypted": "unreadable-ciphertext"})
    assert row["event_metadata"]["previous_readable"] is False
    assert row["event_metadata"]["rotated"] is None, "unknown must be reported as unknown"


def test_the_hard_delete_row_is_written_after_the_delete_succeeds(client):
    """Written first, a failed delete left a row asserting a removal that had not happened.
    Over-reporting and under-reporting are both wrong; capture early, record late."""
    import inspect

    from app.modules.identity import users_router

    source = inspect.getsource(users_router.remove_user)
    assert source.index("await store.delete(user_id)") < source.index("audit.record(")
    assert "removed_email, removed_role = user.email" in source, "capture before the delete"


def test_a_team_role_change_records_what_it_changed_from(client):
    """The shared helper diffed against an empty dict, so every team demotion recorded from: null. The
    identity-side equivalent has always captured the previous role, and an access review needs it."""
    import inspect

    from app.modules.teams import router as teams_router

    source = inspect.getsource(teams_router.update_member)
    assert "await svc.members(team_id)" in source
    assert "before={" in source


def test_no_operator_reason_travels_in_a_query_string():
    """Query strings are written verbatim into Caddy and Cloudflare access logs, which sit outside this
    store's retention window and outside its erasure path. That is the same argument the stdout mirror
    makes for carrying no labels or reasons."""
    from pathlib import Path

    modules = Path(__file__).resolve().parents[1] / "app" / "modules"
    offenders = [path.name for path in modules.rglob("*.py")
                 if "reason: str | None = Query(" in path.read_text()]
    assert not offenders, f"reason must be a body field or a header, not a query parameter: {offenders}"


def test_the_audit_store_has_its_synchronous_half_wired(client):
    """The billing endpoints are sync and write through it. Nothing asserted the wiring, so a refactor
    moving one line in main.py would have made add_sync raise, record_sync swallow it, and every
    payment-link row disappear silently."""
    store = client.app.state.audit
    if hasattr(store, "sync_sessionmaker"):
        assert store.sync_sessionmaker is not None, "the sync half of the audit store is unwired"
    else:
        assert hasattr(store, "add_sync"), "the in-memory store must still accept sync writes"


def test_no_stray_extensionless_file_is_committed():
    """A 697-line copy of a test file was committed as qiko-core/gmail by a `> gmail` redirect typo.
    With no .py extension, ruff did not lint it and pytest did not collect it, so it sat in main
    invisibly, listing coverage that was already done as still missing."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    allowed = {"Dockerfile", "Makefile", "LICENSE", "README", "uv.lock", ".dockerignore",
               ".gitignore", ".python-version", ".env.example"}
    strays = [entry.name for entry in root.iterdir()
              if entry.is_file() and not entry.suffix and entry.name not in allowed]
    assert not strays, f"unexplained extensionless files in qiko-core: {strays}"
