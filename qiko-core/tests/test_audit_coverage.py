"""Every mutating route is either audited or explicitly excused, in writing.

This is the test that makes the audit trail defensible rather than merely present. An auditor's
question is never "show me a log line", it is "show me every privileged action in the period", and the
answer is only as good as the completeness of the population. Before this, six of 168 mutating
endpoints were audited and there was no way to know which 162 were missing without reading them all.

Adding a mutating endpoint now fails CI until someone writes down which it is. That converts a silent
gap into a one-line decision, and the decision is reviewable in a diff.
"""
import pytest

from app.main import create_app
from app.modules.audit import registry
from app.modules.audit.service import CRITICAL, USER, AuditEvent, build_row, diff, fingerprint_of

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# Routes that deliberately write no audit event, each with the reason. Keep the reason specific: "not
# needed" is not a reason, and the next person cannot tell an omission from a decision.
NOT_AUDITED: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/knowledge/search"): "read, persists nothing",
    ("POST", "/api/v1/excel/search"): "read, persists nothing",
    ("POST", "/api/v1/excel/analytics"): "read, persists nothing",
    ("POST", "/api/v1/tenants/{tenant_id}/signals/summarize"): (
        "service-to-service AI draft for jm-backend (JM2-1065); persists nothing durable here, "
        "only an in-memory idempotency cache, the resulting IntentSignal lives in jm-backend"),
    ("POST", "/api/v1/tenants/{tenant_id}/insights/property"): (
        "service-to-service AI draft for jm-backend (JM2-1042); persists nothing durable here, "
        "only an in-memory idempotency cache, the resulting cached insight lives in jm-backend"),
    ("POST", "/api/v1/tenants/{tenant_id}/signals/{request_id}/outcome"): (
        "quality-tracking log, not a security-relevant event; in-memory only, same durability as "
        "the summarize/insight caches it reports against"),
    ("POST", "/api/v1/tenants/{tenant_id}/insights/{request_id}/outcome"): (
        "quality-tracking log, not a security-relevant event; in-memory only, same durability as "
        "the summarize/insight caches it reports against"),

    # Volume. These are 99% of writes and close to 0% of evidential value; auditing them would drown
    # the trail that the CRITICAL events live in. Content is already durable in its own tables.
    ("POST", "/api/v1/chat/ask"): "two message rows per call, ~40k/day at 1k users; content lives in messages",
    ("POST", "/api/v1/chat/conversations"): "idempotent find-or-create; the row is the record",
    ("POST", "/api/v1/public/chat"): "volume is set by strangers, so auditing it is a self-inflicted DoS on the audit table",
    ("POST", "/api/v1/voice/speak"): "per utterance, sub-second cadence",
    ("POST", "/api/v1/rfp/packs/{pack_id}/chat"): "conversational turns, capped at 500 per pack",
    ("POST", "/api/v1/finance/{agent_id}/chat"): "conversational turns over financial documents; the upload and the deletion are audited instead",
    ("POST", "/api/v1/intelligence/agents/{agent_id}/chat/ask"): "conversational turns over captured signals; the signal capture and source changes are audited instead",
    ("PUT", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}/draft"): (
        "autosave-shaped; the meaningful events are lock/unlock, which are ~111 per tender instead of thousands"),
    ("POST", "/api/v1/notifications/{notification_id}/read"): "read-tracking; read_at is already the record",
    ("POST", "/api/v1/notifications/read-all"): "bulk read-tracking; nobody has ever litigated who marked a notification read",
    ("POST", "/api/v1/auth/refresh"): "one per token expiry per tab; the login itself is now audited, and a revoked session already logs",
    ("POST", "/api/v1/channels/slack/webhook"): "external Slack Events API callback; signature-verified and idempotent, payloads are stored in slack_channel_messages",
    ("POST", "/api/v1/tenants/{tenant_id}/activity"): (
        "volume (JM2-1131): one row per screen/property/calculator-step visit, thousands per "
        "investor per day; content is already durable in investor_activity_events"),
    ("POST", "/api/v1/tenants/{tenant_id}/activity/intent-signals"): (
        "service-to-service AI draft (JM2-1131), same shape as signals/summarize; persists "
        "nothing durable here, reads investor_activity_events and returns a generated result"),
}


def _mutating_routes(app) -> set[tuple[str, str]]:
    routes = set()
    for route in app.routes:
        for method in getattr(route, "methods", set()) & MUTATING:
            path = getattr(route, "path", "")
            if path.startswith("/api/v1"):
                routes.add((method, path))
    return routes


def test_every_mutating_route_is_audited_or_excused_in_writing():
    """The parts of this that are not yet instrumented are listed in AUDIT_BACKLOG with a priority, so
    the gap is visible in the repository rather than only in a report."""
    app = create_app()
    routes = _mutating_routes(app)
    accounted = set(NOT_AUDITED) | set(AUDIT_BACKLOG) | set(LEGACY_AUDITED)
    unaccounted = sorted(routes - accounted - set(INSTRUMENTED))
    assert not unaccounted, (
        "these mutating routes are neither audited, nor backlogged, nor excused. Add them to "
        "INSTRUMENTED, AUDIT_BACKLOG or NOT_AUDITED with a reason:\n  " +
        "\n  ".join(f"{method} {path}" for method, path in unaccounted))


def test_nothing_is_declared_twice():
    sets = {"NOT_AUDITED": set(NOT_AUDITED), "AUDIT_BACKLOG": set(AUDIT_BACKLOG),
            "LEGACY_AUDITED": set(LEGACY_AUDITED), "INSTRUMENTED": set(INSTRUMENTED)}
    for first in sets:
        for second in sets:
            if first < second:
                overlap = sets[first] & sets[second]
                assert not overlap, f"{first} and {second} both claim: {overlap}"


# Modules that write audit rows, and how many of their mutating routes do. Counted per module rather
# than globally, because a single total can be kept in step with itself while drifting from reality:
# an earlier version compared len(INSTRUMENTED) against a sum I updated at the same time, so eleven
# credential routes stayed listed as backlog for a whole release after they were instrumented, and
# nothing noticed. A ledger that can be wrong in the safe direction is still wrong.
AUDIT_WRITERS: dict[str, int] = {
    # 8 with the worker availability toggle, which is written in the agent store's transaction.
    "admin/router.py": 8,
    # These three are written inside the STORE transaction rather than by a router call, which is the
    # property that made them worth folding in rather than re-instrumenting at the call site.
    "identity/admin_org_router.py": 2,
    "billing/router.py": 4,
    "agents/router.py": 19,
    "identity/users_router.py": 3,
    "teams/router.py": 3,
    "knowledge/router.py": 1,
    "chat/router.py": 1,
    "rfp/router.py": 7,
    "finance/router.py": 1,
    "intelligence/router.py": 13,
    "agentcore/batch_router.py": 1,
    # One route each, though login writes three different events (success, bad password, bad 2FA).
    "identity/router.py": 1,
    "identity/onboarding_router.py": 1,
    "identity/twofa_router.py": 1,
}


def test_the_instrumented_set_matches_the_source():
    """Nothing else ties this set to reality: a route could be declared instrumented with no code
    behind it, or instrumented in code while still listed as a gap."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "modules"
    # Three routes are audited inside the STORE's transaction rather than by a call in their router,
    # which is the property that made folding them in better than re-instrumenting at the call site.
    # For those, the writer to look at is stores.py.
    WRITTEN_IN_STORE = {"identity/admin_org_router.py", "admin/router.py"}
    stores = (Path(__file__).resolve().parents[1] / "app" / "db" / "stores.py").read_text()
    for relative, count in AUDIT_WRITERS.items():
        text = (root / relative).read_text()
        if relative in WRITTEN_IN_STORE:
            text += stores
        # Counted across every writer name, because billing uses the synchronous path and the
        # credential and team helpers each have their own.
        writes = sum(text.count(marker) for marker in (
            "audit.record(", "audit.record_sync(", "credential_audit(",
            "record_credential_exercised(", "_record_access(", "audit_row=build_record",
            "audit=build_record if audited", "_record_governance(",
            # Erasure is enqueued rather than written in the handler, so the marker is the enqueue: the
            # row itself is written by the worker inside the maintenance transaction.
            '"erase_audit_subject"',
            # The store-side writers, for the routes audited inside a transaction.
            "_platform_access_row(", "_worker_availability_row(",
            # worker-api-key generate/revoke always audit (no "if audited" gate: unlike the
            # free-form config patch, every call here is a real change worth recording).
            "audit=build_record)"))
        assert writes >= count, f"{relative} declares {count} audited routes but writes {writes} times"

    # /auth routes are split across three modules, so the first path segment is not enough on its own.
    EXPLICIT = {
        # /agents/feedback is served by agentcore/batch_router.py, not agents/router.py, so the first
        # path segment is misleading here in the same way it is for /auth.
        "/api/v1/agents/feedback": "agentcore/batch_router.py",
        "/api/v1/admin/org/{email}": "identity/admin_org_router.py",
        "/api/v1/auth/login": "identity/router.py",
        "/api/v1/auth/reset-password": "identity/onboarding_router.py",
        "/api/v1/auth/2fa/verify-setup": "identity/twofa_router.py",
    }
    declared_by_module: dict[str, int] = {}
    for _method, route in INSTRUMENTED:
        segment = route.split("/api/v1/")[1].split("/")[0]
        module = EXPLICIT.get(route) or {
            "admin": "admin/router.py", "billing": "billing/router.py",
            "agents": "agents/router.py", "identity": "identity/users_router.py",
            "teams": "teams/router.py", "knowledge": "knowledge/router.py",
            "chat": "chat/router.py", "rfp": "rfp/router.py",
            "finance": "finance/router.py",
            "intelligence": "intelligence/router.py"}[segment]
        declared_by_module[module] = declared_by_module.get(module, 0) + 1
    assert declared_by_module == AUDIT_WRITERS, (
        f"the ledger and the code disagree: declared {declared_by_module}, expected {AUDIT_WRITERS}")


def test_no_backlogged_route_is_already_audited():
    """The failure this exists for: a route gets instrumented and the ledger is never updated, so the
    file understates coverage and the next person re-does work that is already done."""
    audited_modules = {relative.split("/")[0] for relative in AUDIT_WRITERS}
    for method, route in AUDIT_BACKLOG:
        segment = route.split("/api/v1/")[1].split("/")[0]
        if segment not in audited_modules:
            continue
        # Modules that write audit rows must not also carry backlogged routes with an audited shape.
        assert "-credentials" not in route, (
            f"{method} {route} looks instrumented but is still listed as a gap")


def test_every_excuse_says_something():
    for route, reason in {**NOT_AUDITED, **AUDIT_BACKLOG, **LEGACY_AUDITED}.items():
        assert len(reason) > 20, f"{route} needs a real reason, got {reason!r}"


# --- the registry itself ------------------------------------------------------------------------

def test_every_action_is_internally_consistent():
    for action, spec in registry.REGISTRY.items():
        assert spec.action == action, "the key and the action must agree"
        assert spec.category in registry.CATEGORIES, f"{action} has an unknown category"
        assert spec.target_type, f"{action} needs a target type"
        assert spec.durability in {registry.CRITICAL, registry.STANDARD, registry.EXTERNAL}


def test_the_only_transactional_actions_are_the_ones_that_really_are():
    """The inverse of the source-walking test below, kept small on purpose.

    This used to assert a list of actions equalled CRITICAL, which was a test of a constant against a
    hand-written copy of itself. It passed for a whole release while ten of those actions were written
    on the losable path. What is worth pinning is the one class that genuinely is transactional, so a
    later edit cannot quietly move it off that path.
    """
    for action in (registry.CREDENTIAL_SET, registry.CREDENTIAL_REMOVED):
        assert registry.spec_for(action).durability == CRITICAL


def test_actions_whose_effect_is_at_a_third_party_are_not_pretended_to_be_transactional():
    """Stripe has already created the link when our transaction rolls back, so claiming atomicity
    would be a lie in the docstring rather than a property of the code. Those actions are recorded as
    an attempt and then an outcome instead, which is what actually answers "did the money move" after
    a timeout."""
    for action in (registry.PAYMENT_LINK_ATTEMPTED, registry.PAYMENT_LINK_CREATED,
                   registry.CHECKOUT_STARTED, registry.SUBSCRIPTION_CANCELLED,
                   registry.SUBSCRIPTION_RESUMED):
        assert registry.spec_for(action).durability == registry.EXTERNAL


def test_a_payment_link_records_an_attempt_before_the_provider_is_called():
    """A timeout is the case that matters: the link may exist and the customer may already have been
    emailed. An attempt with no matching outcome is the row that sends someone to look."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "modules" / "billing" / "router.py").read_text()
    attempt = source.index("PAYMENT_LINK_ATTEMPTED")
    call = source.index("links.create(")
    outcome = source.index("PAYMENT_LINK_CREATED")
    assert attempt < call < outcome, "the attempt must be recorded before the provider call"
    assert "outcome=audit.FAILURE" in source, "a provider failure must be recorded, not just raised"


def test_spend_and_authority_rows_carry_their_read_gate():
    """An audit row contains the before/after of what it records, so reading it is reading that. This
    exact mistake was made three times in this console before the rule was written down."""
    assert registry.spec_for(registry.COST_CAP_SET).read_capability is not None
    assert registry.spec_for(registry.PLATFORM_ACCESS_GRANTED).read_capability is not None
    assert registry.spec_for(registry.PAYMENT_LINK_CREATED).read_capability is not None


def test_unreadable_actions_are_computed_for_the_caller():
    from app.modules.identity.admin_rbac import Capability

    def only_customers(capability):
        return capability is Capability.view_customers

    hidden = registry.unreadable_actions(only_customers)
    assert registry.COST_CAP_SET in hidden
    assert registry.PLATFORM_ACCESS_GRANTED in hidden
    assert registry.LOGIN_FAILED not in hidden, "auth events are not gated behind a narrow capability"


# --- redaction ------------------------------------------------------------------------------------

@pytest.mark.parametrize("key", [
    "password", "password_hash", "totp_secret", "api_key", "apiKey", "access_token",
    "refresh_token", "client_secret", "slack_bot_token_encrypted", "gmail_app_password_encrypted",
    "authorization", "cookie", "x-hub-signature", "private_key", "bearer_token", "credential",
    "vapi_api_key_encrypted", "webhook_secret", "csrf_token", "session_token",
])
def test_a_secret_shaped_key_never_reaches_the_row(key):
    row = build_row(AuditEvent(action=registry.WORKER_CONFIG_CHANGED, target_id="w1",
                               metadata={key: "super-secret-value"}))
    assert "super-secret-value" not in str(row), f"{key} leaked into the audit row"


@pytest.mark.parametrize("value", [
    "sk_live_abc123", "sk_test_abc123", "whsec_abc123", "xoxb-1-2-3", "ghp_abcdef",
    "eyJhbGciOiJIUzI1NiJ9.payload", "-----BEGIN RSA PRIVATE KEY-----",
])
def test_a_secret_shaped_value_never_reaches_the_row(value):
    """Belt and braces over the key screen: someone will eventually put a token under an innocent key."""
    row = build_row(AuditEvent(action=registry.WORKER_CONFIG_CHANGED, target_id="w1",
                               metadata={"note": value}))
    assert value not in str(row)


def test_the_diff_is_restricted_to_the_actions_allowlist():
    """The alternative is serialising an object, and a worker config is a free-form dict holding
    encrypted credentials.

    `tone` used to be the example here. It is no longer diffable: the config action's allowlist was
    narrowed to the SCALAR settings, because copying a tenant's prose into a second store is the
    duplication the diff-not-snapshot rule exists to prevent. The prose fields are named in metadata
    instead. gate_threshold is the better example anyway, since its value is the actionable part.
    """
    changed = diff(registry.WORKER_CONFIG_CHANGED,
                   {"gate_threshold": 0.7, "tone": "formal", "slack_bot_token_encrypted": "old"},
                   {"gate_threshold": 0.4, "tone": "casual", "slack_bot_token_encrypted": "new"})
    assert changed == {"gate_threshold": {"from": 0.7, "to": 0.4}}


def test_only_changed_fields_appear():
    changed = diff(registry.WORKER_STATUS_CHANGED, {"status": "ready"}, {"status": "ready"})
    assert changed == {}


def test_a_secret_fingerprint_distinguishes_rotation_from_a_re_save(monkeypatch):
    """A bare changed=true cannot tell an incident responder whether the value was actually rotated."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "encryption_key", "Enc" + "rypt-Z9y8X7w6V5u4T3s2R1q0P9o8N7m6")
    first = fingerprint_of("hunter2")
    assert first == fingerprint_of("hunter2"), "stable for the same value"
    assert first != fingerprint_of("hunter3"), "different for a different value"
    assert first and len(first) == 12 and "hunter2" not in first


def test_no_fingerprint_at_all_rather_than_one_under_a_public_key(monkeypatch):
    """The fallback used to be the constant "audit", which turns the fingerprint into an offline
    verification oracle for any low-entropy secret. No fingerprint is better than that one."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "encryption_key", "")
    assert fingerprint_of("hunter2") is None


def test_an_oversized_single_value_is_capped():
    """A tenant free-text field is not a place to hide a megabyte."""
    row = build_row(AuditEvent(action=registry.DOCUMENT_INGESTED, target_id="d1",
                               metadata={"blob": "x" * 20_000}))
    assert len(row["event_metadata"]["blob"]) == 2_000


def test_oversized_metadata_overall_is_truncated_visibly():
    """Truncated explicitly rather than silently, so a reader knows something was dropped."""
    row = build_row(AuditEvent(action=registry.DOCUMENT_INGESTED, target_id="d1",
                               metadata={f"field{i}": "y" * 500 for i in range(40)}))
    assert row["event_metadata"]["truncated"] is True


def test_the_message_is_rendered_at_write_time():
    """Fixed at the moment it happened, so a later rename cannot rewrite history and a CSV export reads
    without the UI."""
    row = build_row(AuditEvent(action=registry.TENANT_ROLE_CHANGED, actor_type=USER,
                               actor_label="ops@qiko.ai", target_label="user@acme.invalid"))
    assert row["message"] == "ops@qiko.ai changed the role of user@acme.invalid"


def test_an_unregistered_action_is_refused():
    with pytest.raises(KeyError):
        build_row(AuditEvent(action="something.invented"))


# --- the declared state of the world ---------------------------------------------------------------

# Writes to audit_events today. Verified against the source, not merely declared: a route could
# otherwise be moved into this set with no code behind it.
INSTRUMENTED: set[tuple[str, str]] = {
    ("POST", "/api/v1/admin/customers/{user_id}/studio"),
    ("DELETE", "/api/v1/admin/customers/{user_id}"),
    ("PUT", "/api/v1/admin/cost-caps/{tenant_id}"),
    ("DELETE", "/api/v1/admin/cost-caps/{tenant_id}"),
    ("PUT", "/api/v1/admin/users/{user_id}/role"),
    ("PUT", "/api/v1/admin/workers/{tenant_id}/{agent_id}/status"),
    ("POST", "/api/v1/billing/payment-links"),
    ("POST", "/api/v1/billing/payment-links/mark-paid"),
    ("POST", "/api/v1/billing/invoices"),
    ("POST", "/api/v1/billing/invoices/reconcile"),
    ("POST", "/api/v1/agents/{agent_id}/vapi-credentials"),
    ("POST", "/api/v1/agents/{agent_id}/salesforce-credentials"),
    ("DELETE", "/api/v1/agents/{agent_id}/salesforce-credentials"),
    ("POST", "/api/v1/agents/{agent_id}/calendly-credentials"),
    ("DELETE", "/api/v1/agents/{agent_id}/calendly-credentials"),
    ("POST", "/api/v1/agents/{agent_id}/clickup-credentials"),
    ("DELETE", "/api/v1/agents/{agent_id}/clickup-credentials"),
    ("POST", "/api/v1/agents/{agent_id}/slack-credentials"),
    ("DELETE", "/api/v1/agents/{agent_id}/slack-credentials"),
    ("POST", "/api/v1/agents/{agent_id}/gmail-credentials"),
    ("DELETE", "/api/v1/agents/{agent_id}/gmail-credentials"),
    ("POST", "/api/v1/agents/{agent_id}/worker-api-key"),
    ("DELETE", "/api/v1/agents/{agent_id}/worker-api-key"),
    ("PUT", "/api/v1/identity/users/{user_id}/role"),
    ("DELETE", "/api/v1/identity/users/{user_id}"),
    ("POST", "/api/v1/identity/users/invite"),
    ("POST", "/api/v1/teams/{team_id}/members"),
    ("PUT", "/api/v1/teams/{team_id}/members/{user_id}"),
    ("DELETE", "/api/v1/teams/{team_id}/members/{user_id}"),
    ("POST", "/api/v1/agents/{agent_id}/salesforce-credentials/test"),
    ("POST", "/api/v1/agents/{agent_id}/calendly-credentials/test"),
    ("POST", "/api/v1/agents/{agent_id}/clickup-credentials/test"),
    ("POST", "/api/v1/agents/{agent_id}/slack-credentials/test"),
    ("POST", "/api/v1/agents/{agent_id}/gmail-credentials/test"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/sources/{key}"),
    ("DELETE", "/api/v1/intelligence/agents/{agent_id}/sources/{key}"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/sources/{key}/settings"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/sources/{key}/verify"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/sources/{key}/test"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/documents"),
    ("DELETE", "/api/v1/intelligence/agents/{agent_id}/documents/{doc_id}"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/sources/slack/channels"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/pipeline/runs"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/pipeline/runs/{run_id}/resume"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/research/runs"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/research/runs/{run_id}/accept"),
    ("POST", "/api/v1/intelligence/agents/{agent_id}/research/runs/{run_id}/backlog"),
    ("PUT", "/api/v1/agents/{agent_id}/config"),
    ("POST", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}/lock"),
    ("POST", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}/unlock"),
    ("POST", "/api/v1/rfp/packs/{pack_id}/sections/{section_id}/lock-all"),
    ("PUT", "/api/v1/rfp/packs/{pack_id}/stage"),
    ("PUT", "/api/v1/rfp/packs/{pack_id}/outcome"),
    ("POST", "/api/v1/agents/feedback"),
    ("POST", "/api/v1/rfp/packs/{pack_id}/feedback"),
    ("PATCH", "/api/v1/admin/customers/{customer_id}/workers/{agent_id}/enabled"),
    ("PUT", "/api/v1/admin/org/{email}"),
    ("DELETE", "/api/v1/admin/org/{email}"),
    ("DELETE", "/api/v1/knowledge/documents/{doc_id}"),
    ("DELETE", "/api/v1/chat/history/{conversation_id}"),
    ("DELETE", "/api/v1/rfp/packs/{pack_id}"),
    ("DELETE", "/api/v1/finance/{agent_id}/files"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/reset-password"),
    ("POST", "/api/v1/auth/2fa/verify-setup"),
    ("POST", "/api/v1/admin/audit/erase"),
}

# Audited, but into a table that predates the unified stream. Folding these in is leg E2: until then,
# claiming them as "instrumented" would assert a single stream that does not exist. Each is genuinely
# recorded, so they are neither a gap nor yet the thing this change is building.
LEGACY_AUDITED: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/consent"):
        "consent_records, which is legal evidence with its own append-only guarantees and must not move",
    ("POST", "/api/v1/consent/anonymous"):
        "consent_records, same; the audit trail should reference a decision_id rather than copy it",
}


# Not yet instrumented, with the wave each belongs to. Listed so the gap is visible in the
# repository rather than only in a report, and so adding a route cannot quietly join it.
AUDIT_BACKLOG: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/channels/teams/test"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("DELETE", "/api/v1/identity/users/pending/{email}"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams/invites/accept"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams/invites/set-password"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams/{team_id}/invites"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/auth/2fa/backup-codes/regenerate"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/2fa/exchange"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/2fa/setup"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/forgot-password"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/signup"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/verify-email"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("DELETE", "/api/v1/agents/{agent_id}/sources/{kind}/{source_id}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/assignments/pack/{pack_id}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/assignments/section/{pack_id}/{section_id}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/finance/{agent_id}/history"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/rfp/packs/{pack_id}/sections/{section_id}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/sales-intelligence/{agent_id}/sources/{source_key}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("POST", "/api/v1/billing/checkout"): (
        "CRITICAL money: leg E2 wave 1. Nothing records who moved or claimed money."),
    ("POST", "/api/v1/billing/subscription/activate"): (
        "CRITICAL money: leg E2 wave 1. Nothing records who moved or claimed money."),
    ("POST", "/api/v1/billing/subscription/cancel"): (
        "CRITICAL money: leg E2 wave 1. Nothing records who moved or claimed money."),
    ("POST", "/api/v1/billing/subscription/resume"): (
        "CRITICAL money: leg E2 wave 1. Nothing records who moved or claimed money."),
    ("POST", "/api/v1/billing/webhook/stripe"): (
        "CRITICAL money: leg E2 wave 1. Nothing records who moved or claimed money."),
    ("DELETE", "/api/v1/channels/teams/webhook"): (
        "CRITICAL secret: leg E2 wave 2. Persists or clears a third-party credential, two of them unauthenticated."),
    ("PUT", "/api/v1/channels/teams/webhook"): (
        "CRITICAL secret: leg E2 wave 2. Persists or clears a third-party credential, two of them unauthenticated."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/salesforce/connect"): (
        "CRITICAL secret: leg E2 wave 2. Persists or clears a third-party credential, two of them unauthenticated."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/salesforce/disconnect"): (
        "CRITICAL secret: leg E2 wave 2. Persists or clears a third-party credential, two of them unauthenticated."),
    ("PUT", "/api/v1/agents/{agent_id}/sources/persona"): (
        "HIGH config: leg E2. Free-form patch that can reach any config key."),
    ("PATCH", "/api/v1/sales-intelligence/{agent_id}/ingest-filters"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/opportunities"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("PATCH", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}/archive"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("PATCH", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}/assign-reviewer"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}/notes"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}/push-to-salesforce"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}/restore"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}/review"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/opportunities/{opportunity_id}/transition"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/scan/ted"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/scan/ungm"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/scan/{source_key}"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/sales-intelligence/{agent_id}/sources"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("PATCH", "/api/v1/sales-intelligence/{agent_id}/sources/{source_key}"): (
        "MEDIUM: already recorded in sales_intel_activity_logs; folding into the central trail is leg E2."),
    ("POST", "/api/v1/admin/org/accept"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/admin/org/bootstrap"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/admin/org/invite"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/agents"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/agents/batch-answer"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/agents/batch-export"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PUT", "/api/v1/agents/{agent_id}/calendly-event-type"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/agents/{agent_id}/ready"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/agents/{agent_id}/sources/behaviors"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/agents/{agent_id}/sources/faqs"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/agents/{agent_id}/sources/policies"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/agents/{agent_id}/sources/websites"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/assignments/bulk"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/assignments/send-reminder"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PUT", "/api/v1/assignments/{assignment_id}"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PUT", "/api/v1/assignments/{assignment_id}/status"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/auth/logout"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PATCH", "/api/v1/auth/me"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/calendly/book"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/clickup/task"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/gmail/send"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/interakt/webhook"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/sessions/{external_id}/worker"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/slack/link"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/slack/send"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/whatsapp/send"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/channels/whatsapp/webhook"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/chat/files"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PATCH", "/api/v1/crm/actions/{action_id}"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PATCH", "/api/v1/crm/contacts/{contact_id}"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/crm/contacts/{contact_id}/actions"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/crm/contacts/{contact_id}/summary"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/crm/contacts/{contact_id}/sync-salesforce"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/excel/report"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/excel/upload"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/finance/{agent_id}/upload"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/knowledge/evaluate"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/knowledge/ingest"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/knowledge/ingest-file"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/leads"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/marketing/labs-contact"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/ask"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/brief"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/compliance"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/confirm-assignments"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/extract"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/extract-url"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/generate"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PATCH", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}/generate"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/score"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/sections"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PATCH", "/api/v1/rfp/packs/{pack_id}/sections/{section_id}"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/sections/{section_id}/generate"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/sections/{section_id}/questions"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("PUT", "/api/v1/rfp/packs/{pack_id}/sections/{section_id}/reviewer"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/signal/export/{scan_id}"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/signal/projects"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
    ("POST", "/api/v1/signal/scan"): (
        "MEDIUM: leg E2. State change with an identifiable actor, not yet instrumented."),
}


# --- what the security gate found -------------------------------------------------------------------

def test_a_reader_cannot_count_the_rows_they_are_not_allowed_to_see():
    """Excluding rows in SQL is pointless if the response hands back a sequential id: a reader sees
    ids 1, 2, 5, 9 and learns exactly how many hidden events sit between them."""
    from app.db.stores import _audit_json

    class Row:
        id = 42
        event_id = "e-1"
        action = registry.LOGIN_SUCCEEDED
        category = registry.AUTH
        outcome = "success"
        message = "x signed in"
        occurred_at = __import__("datetime").datetime(2026, 8, 5, tzinfo=__import__("datetime").timezone.utc)
        actor_type = actor_id = actor_label = on_behalf_of = None
        target_type = "user"
        target_id = target_label = tenant_id = request_id = None
        source_ip = user_agent = route = None
        service = "api"
        environment = "dev"
        changes = event_metadata = {}
        reason = None

    payload = _audit_json(Row())
    assert "id" not in payload, "the sequential id must not be returned"
    # The cursor carries the id, but as an opaque compound the reader has no reason to decompose and
    # which is meaningless without the timestamp it is paired with.
    assert payload["_cursor"].endswith("|42")


def test_secrets_survive_none_of_the_container_shapes():
    """An earlier version walked only dicts and lists, so a tuple or a set carried a value straight
    through, and a set is not even JSON serialisable so the row would have failed at flush."""
    from app.modules.audit.service import _scrub

    for shape in (("sk_live_abc",), {"sk_live_abc"}, frozenset({"sk_live_abc"}),
                  ["sk_live_abc"], {"x": ["sk_live_abc"]}):
        assert "sk_live_abc" not in str(_scrub(shape)), f"leaked through {type(shape).__name__}"


def test_a_secret_in_the_key_is_caught_too():
    from app.modules.audit.service import _scrub

    assert "sk_live_abc" not in str(_scrub({"sk_live_abc": "value"}))


def test_a_secret_in_the_middle_of_a_string_is_caught():
    """The pattern used to be anchored at the start, which misses the shape a token actually arrives
    in: inside an Authorization header value or a sentence."""
    from app.modules.audit.service import _scrub

    assert _scrub("Bearer sk_live_abcdef") == "[redacted]"
    assert _scrub({"note": "the key is ghp_abcdef"})["note"] == "[redacted]"


def test_an_object_is_not_handed_to_the_serialiser_intact():
    """A dataclass or a model reaching the JSON column would dump every attribute it has."""
    from dataclasses import dataclass as dc

    from app.modules.audit.service import _scrub

    @dc
    class Credentials:
        token: str = "sk_live_secret"

    assert "sk_live_secret" not in str(_scrub(Credentials()))


def test_the_diff_allowlist_has_no_from_to_hole():
    """A previous version also admitted top-level "from"/"to" keys, which diff() never produces and
    which therefore only served as a gap wide enough to carry anything."""
    row = build_row(AuditEvent(action=registry.WORKER_STATUS_CHANGED, target_id="w1",
                               changes={"from": "anything at all", "to": "anything at all"}))
    assert row["changes"] == {}


def test_the_message_is_rendered_from_the_scrubbed_diff():
    """Rendering from the raw changes would let a value that _scrub redacted reappear verbatim in a
    column every reader sees, and the diff shape would render a dict into the sentence."""
    row = build_row(AuditEvent(
        action=registry.CREDENTIAL_SET, actor_label="ops@qiko.ai", target_label="Tender Bot",
        changes={"provider": {"from": None, "to": "slack"}}))
    assert row["message"] == "ops@qiko.ai set the slack credential on Tender Bot"


def test_every_template_in_the_registry_renders():
    """One rendering test covered one template. A typo in any of the other forty raises at write time,
    and on the transactional path that would take down the caller's mutation."""
    for action in registry.ACTIONS:
        row = build_row(AuditEvent(action=action, actor_label="a@b", target_label="t",
                                   changes={"provider": "slack"} if "provider" in
                                   registry.spec_for(action).diff_fields else {}))
        assert row["message"] and "{" not in row["message"], f"{action} did not render"


def test_the_source_address_cannot_be_forged_by_a_header():
    """Cloudflare APPENDS to X-Forwarded-For and Caddy forwards it untrimmed, so its leftmost value is
    whatever the client sent. Recording that is attribution poisoning in the store whose only job is
    attribution."""
    from app.modules.audit.service import _client_ip

    class Client:
        host = "203.0.113.9"

    forged = {"x-forwarded-for": "8.8.8.8", "cf-connecting-ip": "203.0.113.9"}
    assert _client_ip(forged, Client()) == "203.0.113.9"
    assert _client_ip({"x-forwarded-for": "8.8.8.8"}, Client()) == "203.0.113.9"
    # A malformed value must not become a stored string that looks like an address.
    assert _client_ip({"cf-connecting-ip": "not-an-ip"}, None) is None


def test_the_stdout_mirror_is_a_pointer_not_a_second_copy(caplog):
    """It used to echo every label, the reason, the IP and the user agent into application logs, which
    sit outside this store's retention and outside its erasure path, and it did so at INFO, which live
    drops entirely."""
    import logging

    from app.modules.audit.service import _mirror

    row = build_row(AuditEvent(action=registry.TENANT_ROLE_CHANGED, actor_label="ops@qiko.ai",
                               target_label="victim@acme.invalid", reason="a private note"))
    with caplog.at_level(logging.WARNING):
        _mirror(row)
    mirrored = caplog.records[-1].audit_event
    assert "ops@qiko.ai" not in str(mirrored) and "victim@acme.invalid" not in str(mirrored)
    assert "a private note" not in str(mirrored)
    assert mirrored["event_id"] == row["event_id"], "it must still point at the row"
    # WARNING, not INFO: live runs LOG_LEVEL=WARNING, so at INFO the backstop did not exist where it
    # was needed.
    assert caplog.records[-1].levelno == logging.WARNING


def test_every_critical_action_with_a_call_site_has_a_transactional_one():
    """CRITICAL means "written in the caller's transaction", which is a claim about the code.

    The previous version of this file asserted `spec.durability == CRITICAL`, i.e. a constant in the
    module next door. Ten actions were declared CRITICAL and written through `record()`, the path that
    is explicitly allowed to lose the row, and the test was green throughout. It read as coverage of a
    property that did not hold, which is worse than no test.

    This walks the source instead: if an action is written anywhere, and it is declared CRITICAL, then
    at least one of its call sites must be transactional. Actions with no call site yet claim nothing
    and are left alone.
    """
    from pathlib import Path

    modules = Path(__file__).resolve().parents[1] / "app" / "modules"
    sources = {path: path.read_text() for path in modules.rglob("*.py")}

    # The transactional writers: the store adds the row to the caller's own session.
    transactional_markers = ("credential_audit(", "audit=audit_credentials", "store.add_in(",
                             "audit.record_in(", "audit_row=build_record",
                             "audit=build_record if audited")

    offenders = []
    for action, spec in registry.REGISTRY.items():
        constant = next((name for name, value in vars(registry).items()
                         if isinstance(value, str) and value == action and name.isupper()), None)
        if constant is None:
            continue
        written_in = {path: text for path, text in sources.items()
                      if f"audit_actions.{constant}" in text or f"registry.{constant}" in text}
        if not written_in:
            continue  # declared but not yet used: nothing is claimed
        if spec.durability != registry.CRITICAL:
            continue
        if not any(any(marker in text for marker in transactional_markers)
                   for text in written_in.values()):
            offenders.append(action)

    assert not offenders, (
        "these actions are declared CRITICAL but every call site uses the non-transactional writer. "
        "Either write them in the caller's transaction or declare them STANDARD:\n  " +
        "\n  ".join(sorted(offenders)))


def test_no_action_is_given_a_diff_it_cannot_keep(caplog):
    """An action written with changes while declaring no diff_fields silently records nothing.

    PLATFORM_ACCESS_REVOKED shipped that way: the row said access had been revoked without saying what
    was revoked, which for a revoke is the entire content since the row it describes no longer exists.
    The allowlist doing its job looks identical to the allowlist being empty.

    Checked inside diff() rather than by walking call sites. A first version searched the source for
    `diff(audit_actions.X` and missed this exact case, because the store passes the action through a
    variable, so the literal never appears. A runtime check catches it however the call is spelled.
    """
    import logging

    from app.modules.audit.service import diff as audit_diff

    fieldless = [a for a, spec in registry.REGISTRY.items() if not spec.diff_fields]
    assert fieldless, "this test is meaningless if every action declares fields"

    with caplog.at_level(logging.ERROR):
        audit_diff(fieldless[0], {"something": 1}, {"something": 2})
    assert "cannot keep" in caplog.text

    # And the real actions used with a diff must not trip it.
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        audit_diff(registry.PLATFORM_ACCESS_REVOKED,
                   {"role": "viewer", "capabilities": ["view_customers"]},
                   {"role": None, "capabilities": None})
        audit_diff(registry.WORKER_ENABLED_CHANGED, {"enabled": True}, {"enabled": False})
    assert "cannot keep" not in caplog.text
