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
    # Stateless: a read dressed as a POST.
    ("POST", "/api/v1/admin/revenue"): "pure calculator over the request body, writes nothing",
    ("POST", "/api/v1/knowledge/search"): "read, persists nothing",
    ("POST", "/api/v1/excel/search"): "read, persists nothing",
    ("POST", "/api/v1/excel/analytics"): "read, persists nothing",

    # Volume. These are 99% of writes and close to 0% of evidential value; auditing them would drown
    # the trail that the CRITICAL events live in. Content is already durable in its own tables.
    ("POST", "/api/v1/chat/ask"): "two message rows per call, ~40k/day at 1k users; content lives in messages",
    ("POST", "/api/v1/chat/conversations"): "idempotent find-or-create; the row is the record",
    ("POST", "/api/v1/public/chat"): "volume is set by strangers, so auditing it is a self-inflicted DoS on the audit table",
    ("POST", "/api/v1/voice/speak"): "per utterance, sub-second cadence",
    ("POST", "/api/v1/rfp/packs/{pack_id}/chat"): "conversational turns, capped at 500 per pack",
    ("POST", "/api/v1/finance/{agent_id}/chat"): "conversational turns over financial documents; the upload and the deletion are audited instead",
    ("PUT", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}/draft"): (
        "autosave-shaped; the meaningful events are lock/unlock, which are ~111 per tender instead of thousands"),
    ("POST", "/api/v1/notifications/{notification_id}/read"): "read-tracking; read_at is already the record",
    ("POST", "/api/v1/notifications/read-all"): "bulk read-tracking; nobody has ever litigated who marked a notification read",
    ("POST", "/api/v1/auth/refresh"): "one per token expiry per tab; the login and the revocation are audited",
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
    accounted = set(NOT_AUDITED) | set(AUDIT_BACKLOG)
    unaccounted = sorted(routes - accounted - set(INSTRUMENTED))
    assert not unaccounted, (
        "these mutating routes are neither audited, nor backlogged, nor excused. Add them to "
        "INSTRUMENTED, AUDIT_BACKLOG or NOT_AUDITED with a reason:\n  " +
        "\n  ".join(f"{method} {path}" for method, path in unaccounted))


def test_nothing_is_both_excused_and_instrumented():
    overlap = set(NOT_AUDITED) & set(INSTRUMENTED)
    assert not overlap, f"contradictory declarations: {overlap}"


def test_every_excuse_says_something():
    for route, reason in {**NOT_AUDITED, **AUDIT_BACKLOG}.items():
        assert len(reason) > 20, f"{route} needs a real reason, got {reason!r}"


# --- the registry itself ------------------------------------------------------------------------

def test_every_action_is_internally_consistent():
    for action, spec in registry.REGISTRY.items():
        assert spec.action == action, "the key and the action must agree"
        assert spec.category in registry.CATEGORIES, f"{action} has an unknown category"
        assert spec.target_type, f"{action} needs a target type"
        assert spec.durability in {registry.CRITICAL, registry.STANDARD}


def test_money_access_credentials_and_deletions_are_transactional():
    """Getting the durability backwards is the main design risk. A payment-link audit that can silently
    vanish is worthless; a chat-volume audit that can fail a request turns an audit outage into a
    product outage."""
    must_be_critical = {
        registry.PAYMENT_LINK_CREATED, registry.PAYMENT_LINK_MARKED_PAID,
        registry.SUBSCRIPTION_CANCELLED, registry.COST_CAP_SET,
        registry.PLATFORM_ACCESS_GRANTED, registry.PLATFORM_ACCESS_REVOKED,
        registry.TENANT_ROLE_CHANGED, registry.TENANT_MEMBER_ADDED, registry.TENANT_MEMBER_REMOVED,
        registry.CREDENTIAL_SET, registry.CREDENTIAL_REMOVED,
        registry.DOCUMENT_DELETED, registry.RFP_PACK_DELETED, registry.CHAT_HISTORY_DELETED,
        registry.CUSTOMER_SOFT_DELETED, registry.SUBJECT_ERASED,
    }
    for action in must_be_critical:
        assert registry.spec_for(action).durability == CRITICAL, f"{action} must be transactional"


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
    encrypted credentials."""
    changed = diff(registry.WORKER_CONFIG_CHANGED,
                   {"tone": "formal", "slack_bot_token_encrypted": "old"},
                   {"tone": "casual", "slack_bot_token_encrypted": "new"})
    assert changed == {"tone": {"from": "formal", "to": "casual"}}


def test_only_changed_fields_appear():
    changed = diff(registry.WORKER_STATUS_CHANGED, {"status": "ready"}, {"status": "ready"})
    assert changed == {}


def test_a_secret_fingerprint_distinguishes_rotation_from_a_re_save():
    """A bare changed=true cannot tell an incident responder whether the value was actually rotated."""
    first = fingerprint_of("hunter2")
    assert first == fingerprint_of("hunter2"), "stable for the same value"
    assert first != fingerprint_of("hunter3"), "different for a different value"
    assert first and len(first) == 12 and "hunter2" not in first


def test_oversized_metadata_is_truncated_visibly():
    row = build_row(AuditEvent(action=registry.DOCUMENT_INGESTED, target_id="d1",
                               metadata={"blob": "x" * 20_000}))
    assert row["event_metadata"] == {"truncated": True, "original_bytes": pytest.approx(20_014, abs=50)}


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

# Instrumented today.
INSTRUMENTED: set[tuple[str, str]] = {
    ("POST", "/api/v1/admin/customers/{user_id}/studio"),
    ("DELETE", "/api/v1/admin/customers/{user_id}"),
    ("PUT", "/api/v1/admin/cost-caps/{tenant_id}"),
    ("DELETE", "/api/v1/admin/cost-caps/{tenant_id}"),
    ("PUT", "/api/v1/admin/users/{user_id}/role"),
    ("PUT", "/api/v1/admin/workers/{tenant_id}/{agent_id}/status"),
    ("PATCH", "/api/v1/admin/customers/{customer_id}/workers/{agent_id}/enabled"),
    ("PUT", "/api/v1/admin/org/{email}"),
    ("DELETE", "/api/v1/admin/org/{email}"),
    ("POST", "/api/v1/consent"),
    ("POST", "/api/v1/consent/anonymous"),
}


# Not yet instrumented, with the wave each belongs to. Listed so the gap is visible in the
# repository rather than only in a report, and so adding a route cannot quietly join it.
AUDIT_BACKLOG: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/channels/teams/test"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/identity/users/invite"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("DELETE", "/api/v1/identity/users/pending/{email}"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("DELETE", "/api/v1/identity/users/{user_id}"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("PUT", "/api/v1/identity/users/{user_id}/role"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams/invites/accept"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams/invites/set-password"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams/{team_id}/invites"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/teams/{team_id}/members"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("DELETE", "/api/v1/teams/{team_id}/members/{user_id}"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("PUT", "/api/v1/teams/{team_id}/members/{user_id}"): (
        "CRITICAL access: leg E2 wave 3. Changes who can reach a tenant, including a hard delete."),
    ("POST", "/api/v1/auth/2fa/backup-codes/regenerate"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/2fa/exchange"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/2fa/setup"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/2fa/verify-setup"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/forgot-password"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/login"): (
        "CRITICAL auth: leg E2 wave 4. No authentication trail exists at all, which is the standard SOC 2 CC6.1 finding."),
    ("POST", "/api/v1/auth/reset-password"): (
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
    ("DELETE", "/api/v1/chat/history/{conversation_id}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/finance/{agent_id}/files"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/finance/{agent_id}/history"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/knowledge/documents/{doc_id}"): (
        "CRITICAL deletion: leg E2 wave 5. Destroys customer data with no record of who or why."),
    ("DELETE", "/api/v1/rfp/packs/{pack_id}"): (
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
    ("POST", "/api/v1/billing/payment-links"): (
        "CRITICAL money: leg E2 wave 1. Nothing records who moved or claimed money."),
    ("POST", "/api/v1/billing/payment-links/mark-paid"): (
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
    ("DELETE", "/api/v1/agents/{agent_id}/calendly-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/calendly-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/calendly-credentials/test"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("DELETE", "/api/v1/agents/{agent_id}/clickup-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/clickup-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/clickup-credentials/test"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("DELETE", "/api/v1/agents/{agent_id}/gmail-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/gmail-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/gmail-credentials/test"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("DELETE", "/api/v1/agents/{agent_id}/salesforce-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/salesforce-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/salesforce-credentials/test"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("DELETE", "/api/v1/agents/{agent_id}/slack-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/slack-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/slack-credentials/test"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("POST", "/api/v1/agents/{agent_id}/vapi-credentials"): (
        "CRITICAL secret: leg E2 wave 2. Writes or destroys an encrypted integration credential."),
    ("PUT", "/api/v1/agents/{agent_id}/config"): (
        "HIGH config: leg E2. Free-form patch that can reach any config key."),
    ("PUT", "/api/v1/agents/{agent_id}/sources/persona"): (
        "HIGH config: leg E2. Free-form patch that can reach any config key."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/feedback"): (
        "HIGH governance: leg E2. Human sign-off on a bid."),
    ("PUT", "/api/v1/rfp/packs/{pack_id}/outcome"): (
        "HIGH governance: leg E2. Human sign-off on a bid."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}/lock"): (
        "HIGH governance: leg E2. Human sign-off on a bid."),
    ("POST", "/api/v1/rfp/packs/{pack_id}/sections/{section_id}/lock-all"): (
        "HIGH governance: leg E2. Human sign-off on a bid."),
    ("PUT", "/api/v1/rfp/packs/{pack_id}/stage"): (
        "HIGH governance: leg E2. Human sign-off on a bid."),
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
    ("POST", "/api/v1/agents/feedback"): (
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
    ("POST", "/api/v1/rfp/packs/{pack_id}/questions/{question_id}/unlock"): (
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
