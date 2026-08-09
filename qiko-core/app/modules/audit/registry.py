"""The closed registry of auditable actions.

Every audited action is declared here once, and the declaration carries everything the rest of the
system needs: which category it belongs to, who is allowed to READ it, which fields may appear in its
diff, and how it renders as a sentence. Four things that would otherwise be scattered across call
sites, a router, a UI and a policy document, and would drift.

Why a closed set rather than free strings. A typo in a free-form action string produces an audit row
nobody can ever find again, which is worse than no row: it looks like coverage. A closed set makes the
typo a failing test.

Why the read capability lives here. An audit row necessarily contains the before and after of the
thing it records, so reading the row is reading that thing. The cost-cap rows are the worked example:
GET /admin/cost-caps is gated on view_ai_cost because per-account spend reveals unit economics, so
returning those rows on a weaker gate would make the audit trail a way around it. That rule was
discovered twice by review before it was written down; putting it next to the action means the next
action cannot forget it.

Why the diff allowlist lives here. The alternative is serialising an object, and this codebase has
concrete evidence of why that is unsafe: agents.config is a free-form dict that holds encrypted
credentials, which is exactly why the admin display path already has its own field allowlist.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.identity.admin_rbac import Capability

# Categories exist so the UI can group filters and so retention can differ by class without a second
# taxonomy. Kept deliberately short: a category per module would just be the module list again.
AUTH = "auth"
ACCESS = "access"
ADMIN = "admin"
BILLING = "billing"
DATA = "data"
CONFIG = "config"
PRIVACY = "privacy"
CATEGORIES = frozenset({AUTH, ACCESS, ADMIN, BILLING, DATA, CONFIG, PRIVACY})

# How durable a given class of event has to be. See app/modules/audit/service.py: CRITICAL actions are
# written in the caller's transaction so a mutation cannot commit without its audit row, everything
# else is written afterwards and never raises. Getting this backwards is the main design risk: a
# payment-link audit that can silently vanish is worthless, and a chat-volume audit that can fail a
# request turns an audit outage into a product outage.
# Written inside the caller's transaction, so the mutation cannot commit without its row. This is a
# claim about the CODE, not an aspiration: `record()` and `record_sync()` both log an error when a
# CRITICAL action reaches them, and the route-coverage test asserts that every CRITICAL action has a
# transactional call site. An earlier version declared ten actions CRITICAL that were written on the
# weak path, which had two live consequences: the rows could be lost for exactly the events that must
# not be losable, and every routine deletion emitted an ERROR that Sentry turned into an alert,
# drowning the real "audit write failed" it shares a logger with.
CRITICAL = "critical"
# Written after the fact and never raising. Losing one is acceptable; failing the request it observes
# is not. This is the right class for most events, and saying so is better than claiming a guarantee
# the call site does not provide.
STANDARD = "standard"
# Actions whose real effect happens at a third party. Atomicity with our database is impossible by
# construction: Stripe has already created the link when our transaction rolls back. So the honest
# shape is not a single row written transactionally, it is the intent recorded BEFORE the call and the
# outcome after, which is the start/succeed/fail triple the Salesforce push path already uses. A
# timeout is the case that makes this matter: the call may well have succeeded.
EXTERNAL = "external"


@dataclass(frozen=True)
class ActionSpec:
    action: str
    category: str
    target_type: str
    # None means any platform admin who can read the log at all. Otherwise the reader additionally
    # needs this capability, enforced in SQL rather than after the LIMIT.
    read_capability: Capability | None = None
    # The only field names that may appear in this action's diff. Anything else is dropped.
    diff_fields: tuple[str, ...] = ()
    durability: str = STANDARD
    # Rendered into the `message` column at write time, so the sentence is fixed at the moment it
    # happened and survives a later rename, and so a CSV export reads without the UI.
    template: str = ""


def _spec(action: str, category: str, target_type: str, **kwargs) -> ActionSpec:
    return ActionSpec(action=action, category=category, target_type=target_type, **kwargs)


# --- authentication and session ---------------------------------------------------------------------
# There is currently no login trail of any kind, which is the single most commonly raised finding in a
# SOC 2 CC6.1 sample: an auditor asks for authentication successes AND failures and there is nothing to
# hand over. Failures matter more than successes here.
LOGIN_SUCCEEDED = "auth.login_succeeded"
LOGIN_FAILED = "auth.login_failed"
MFA_ENROLLED = "auth.mfa_enrolled"
MFA_FAILED = "auth.mfa_failed"
BACKUP_CODES_REGENERATED = "auth.backup_codes_regenerated"
PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
PASSWORD_CHANGED = "auth.password_changed"
SESSION_REVOKED = "auth.session_revoked"
ACCESS_DENIED = "auth.access_denied"

# --- access and membership ---------------------------------------------------------------------------
PLATFORM_ACCESS_GRANTED = "access.platform_granted"
PLATFORM_ACCESS_REVOKED = "access.platform_revoked"
TENANT_ROLE_CHANGED = "access.tenant_role_changed"
TENANT_MEMBER_ADDED = "access.member_added"
TENANT_MEMBER_REMOVED = "access.member_removed"
INVITE_SENT = "access.invite_sent"
INVITE_ACCEPTED = "access.invite_accepted"

# --- money ----------------------------------------------------------------------------------------
CHECKOUT_STARTED = "billing.checkout_started"
BILLING_PORTAL_OPENED = "billing.portal_opened"
SUBSCRIPTION_CANCELLED = "billing.subscription_cancelled"
SUBSCRIPTION_RESUMED = "billing.subscription_resumed"
PAYMENT_LINK_ATTEMPTED = "billing.payment_link_attempted"
PAYMENT_LINK_CREATED = "billing.payment_link_created"
PAYMENT_LINK_MARKED_PAID = "billing.payment_link_marked_paid"
STRIPE_WEBHOOK_APPLIED = "billing.stripe_webhook_applied"
COST_CAP_SET = "billing.cost_cap_set"
COST_CAP_REMOVED = "billing.cost_cap_removed"

# --- credentials and integrations -------------------------------------------------------------------
CREDENTIAL_SET = "config.credential_set"
CREDENTIAL_REMOVED = "config.credential_removed"
CREDENTIAL_TESTED = "config.credential_tested"
INTEGRATION_CONNECTED = "config.integration_connected"
INTEGRATION_DISCONNECTED = "config.integration_disconnected"

# --- tenant and worker lifecycle ----------------------------------------------------------------------
STUDIO_TOGGLED = "admin.studio_toggled"
CUSTOMER_SOFT_DELETED = "admin.customer_soft_deleted"
WORKER_CREATED = "admin.worker_created"
WORKER_ENABLED_CHANGED = "admin.worker_enabled_changed"
WORKER_STATUS_CHANGED = "admin.worker_status_changed"
WORKER_CONFIG_CHANGED = "config.worker_config_changed"
WORKER_PUBLISHED = "admin.worker_published"

# --- data -------------------------------------------------------------------------------------------
DOCUMENT_INGESTED = "data.document_ingested"
DOCUMENT_DELETED = "data.document_deleted"
RFP_PACK_DELETED = "data.rfp_pack_deleted"
FINANCE_FILES_DELETED = "data.finance_files_deleted"
CHAT_HISTORY_DELETED = "data.chat_history_deleted"
ANSWER_APPROVED = "data.answer_approved"

# --- privacy -----------------------------------------------------------------------------------------
SUBJECT_ERASED = "privacy.subject_erased"
AUDIT_EXPORTED = "privacy.audit_exported"

_SPECS: tuple[ActionSpec, ...] = (
    # Authentication. No diff fields: there is nothing about a login worth recording as a change, and
    # a password is never a value we hold.
    _spec(LOGIN_SUCCEEDED, AUTH, "user", template="{actor} signed in"),
    _spec(LOGIN_FAILED, AUTH, "user", template="Failed sign-in for {target}"),
    _spec(MFA_ENROLLED, AUTH, "user", # Not transactional: enable_twofa commits before the row is written.
          durability=STANDARD, template="{actor} enrolled two-factor authentication"),
    _spec(MFA_FAILED, AUTH, "user", template="Failed two-factor check for {target}"),
    _spec(BACKUP_CODES_REGENERATED, AUTH, "user", durability=CRITICAL,
          template="{actor} regenerated their backup codes"),
    _spec(PASSWORD_RESET_REQUESTED, AUTH, "user", template="Password reset requested for {target}"),
    _spec(PASSWORD_CHANGED, AUTH, "user", # Not transactional: set_password commits before the row is written.
          durability=STANDARD, diff_fields=("method",),
          template="Password changed for {target}"),
    _spec(SESSION_REVOKED, AUTH, "user", template="Session revoked for {target}"),
    _spec(ACCESS_DENIED, AUTH, "endpoint", template="{actor} was denied {target}"),

    # Access. All CRITICAL: these answer "who could get in", which is the question every access review
    # and every incident starts from.
    _spec(PLATFORM_ACCESS_GRANTED, ACCESS, "platform_admin", read_capability=Capability.manage_admins,
          durability=CRITICAL, diff_fields=("role", "capabilities"),
          template="{actor} granted platform access to {target}"),
    _spec(PLATFORM_ACCESS_REVOKED, ACCESS, "platform_admin", read_capability=Capability.manage_admins,
          durability=CRITICAL, template="{actor} revoked platform access for {target}"),
    _spec(TENANT_ROLE_CHANGED, ACCESS, "user", # Not transactional: the identity store commits on its own; making this transactional needs an injected session (leg E4).
          durability=STANDARD, diff_fields=("role",),
          template="{actor} changed the role of {target}"),
    _spec(TENANT_MEMBER_ADDED, ACCESS, "user", # Not transactional: team membership commits in the teams service; same restructuring as above.
          durability=STANDARD, diff_fields=("role",),
          template="{actor} added {target} to a team"),
    _spec(TENANT_MEMBER_REMOVED, ACCESS, "user", # Not transactional: as above, and the hard-delete path commits before the row is written.
          durability=STANDARD,
          template="{actor} removed {target} from a team"),
    _spec(INVITE_SENT, ACCESS, "email", diff_fields=("role",), template="{actor} invited {target}"),
    _spec(INVITE_ACCEPTED, ACCESS, "email", durability=CRITICAL, template="{target} accepted an invitation"),

    # Money. All CRITICAL and all gated on manage_billing, because the amounts are commercial detail.
    _spec(CHECKOUT_STARTED, BILLING, "tenant", read_capability=Capability.manage_billing,
          durability=EXTERNAL, diff_fields=("plan",), template="{actor} started checkout"),
    _spec(BILLING_PORTAL_OPENED, BILLING, "tenant", read_capability=Capability.manage_billing,
          # Worth recording precisely because what happens next is invisible to us: the customer can
          # change or cancel their plan inside Stripe, and this row is the only handoff marker.
          template="{actor} opened the Stripe billing portal"),
    _spec(SUBSCRIPTION_CANCELLED, BILLING, "tenant", read_capability=Capability.manage_billing,
          durability=EXTERNAL, template="{actor} cancelled the subscription"),
    _spec(SUBSCRIPTION_RESUMED, BILLING, "tenant", read_capability=Capability.manage_billing,
          durability=EXTERNAL, template="{actor} resumed the subscription"),
    _spec(PAYMENT_LINK_ATTEMPTED, BILLING, "payment_link", read_capability=Capability.manage_billing,
          durability=EXTERNAL, diff_fields=("amount_cents", "customer_email", "recurring"),
          # Written before the provider is called. If the call times out the money may still have
          # moved, and an attempt with no outcome is exactly the row an operator needs to go and check.
          template="{actor} is creating a payment link"),
    _spec(PAYMENT_LINK_CREATED, BILLING, "payment_link", read_capability=Capability.manage_billing,
          durability=EXTERNAL, diff_fields=("amount_cents", "customer_email", "recurring"),
          template="{actor} created a payment link"),
    _spec(PAYMENT_LINK_MARKED_PAID, BILLING, "payment_link", read_capability=Capability.manage_billing,
          # An operator declaring money received without money moving. If one row in this table ever
          # matters in a dispute, it is this one. Local-only, so it can and must be transactional.
          # Not transactional: the payment-link store is the separate SYNC engine, so it cannot share a transaction with an async write.
          durability=STANDARD, diff_fields=("amount_cents", "status", "links_marked"),
          template="{actor} marked a payment link paid"),
    _spec(STRIPE_WEBHOOK_APPLIED, BILLING, "tenant", read_capability=Capability.manage_billing,
          durability=CRITICAL, diff_fields=("plan", "status"),
          template="Stripe applied {target}"),
    _spec(COST_CAP_SET, BILLING, "cost_cap", read_capability=Capability.view_ai_cost,
          # Not transactional: the cap store commits on its own, and the guard cache is invalidated after.
          durability=STANDARD, diff_fields=("monthly_cap_nano_usd", "alert_threshold_pct"),
          template="{actor} set a spend cap"),
    _spec(COST_CAP_REMOVED, BILLING, "cost_cap", read_capability=Capability.view_ai_cost,
          # Not transactional: as above.
          durability=STANDARD, diff_fields=("monthly_cap_nano_usd",),
          template="{actor} removed a spend cap"),

    # Credentials. The diff never carries a value: see fingerprint_of in service.py.
    _spec(CREDENTIAL_SET, CONFIG, "worker", durability=CRITICAL, diff_fields=("provider", "key"),
          template="{actor} set the {provider} credential on {target}"),
    _spec(CREDENTIAL_REMOVED, CONFIG, "worker", durability=CRITICAL, diff_fields=("provider", "key"),
          template="{actor} removed the {provider} credential from {target}"),
    _spec(CREDENTIAL_TESTED, CONFIG, "worker", diff_fields=("provider", "result"),
          # A decrypt-and-call is the cheapest signal that a leaked encryption key is being exercised.
          template="{actor} tested the {provider} credential on {target}"),
    _spec(INTEGRATION_CONNECTED, CONFIG, "worker", durability=CRITICAL, diff_fields=("provider",),
          template="{actor} connected {provider} to {target}"),
    _spec(INTEGRATION_DISCONNECTED, CONFIG, "worker", durability=CRITICAL, diff_fields=("provider",),
          template="{actor} disconnected {provider} from {target}"),

    # Tenant and worker lifecycle.
    _spec(STUDIO_TOGGLED, ADMIN, "tenant", diff_fields=("is_studio",),
          template="{actor} changed Studio access for {target}"),
    _spec(CUSTOMER_SOFT_DELETED, ADMIN, "tenant", # Not transactional: the customer directory is the separate SYNC engine, so no shared transaction exists.
          durability=STANDARD, diff_fields=("state",),
          template="{actor} deleted the account {target}"),
    _spec(WORKER_CREATED, ADMIN, "worker", diff_fields=("name", "type"),
          template="{actor} created worker {target}"),
    _spec(WORKER_ENABLED_CHANGED, ADMIN, "worker", durability=CRITICAL, diff_fields=("enabled",),
          template="{actor} changed availability of worker {target}"),
    _spec(WORKER_STATUS_CHANGED, ADMIN, "worker", diff_fields=("status",),
          template="{actor} changed the status of worker {target}"),
    _spec(WORKER_PUBLISHED, ADMIN, "worker", diff_fields=("status",),
          template="{actor} published worker {target}"),
    # The widest blast radius in the tenant app: a free-form merge patch that can change the grounding
    # threshold, archive the worker, or write any credential key. Key names only, never values.
    _spec(WORKER_CONFIG_CHANGED, CONFIG, "worker", diff_fields=(
        "archived", "expertise", "industry", "language", "tone", "gate_threshold", "retrieval_k",
        "system_prompt_changed", "opportunity_criteria"),
        template="{actor} changed the configuration of worker {target}"),

    # Data. Deletions are CRITICAL: they are the events a customer disputes.
    _spec(DOCUMENT_INGESTED, DATA, "document", diff_fields=("doc_id", "chunks"),
          template="{actor} ingested {target}"),
    _spec(DOCUMENT_DELETED, DATA, "document", # Not transactional: the knowledge service owns its transaction; the passage count is the evidence, not the atomicity.
          durability=STANDARD, diff_fields=("doc_id", "passages_removed"),
          template="{actor} deleted document {target}"),
    _spec(RFP_PACK_DELETED, DATA, "rfp_pack", # Not transactional: cascades across four services, so there is no single transaction to join.
          durability=STANDARD,
          diff_fields=("sections", "questions", "answers"),
          template="{actor} deleted tender pack {target}"),
    _spec(FINANCE_FILES_DELETED, DATA, "finance_file", # Not transactional: the finance service commits on its own.
          durability=STANDARD, diff_fields=("file_count",),
          template="{actor} deleted financial files"),
    _spec(CHAT_HISTORY_DELETED, DATA, "conversation", # Not transactional: the chat store commits on its own.
          durability=STANDARD, diff_fields=("messages_removed",),
          template="{actor} deleted a conversation"),
    _spec(ANSWER_APPROVED, DATA, "answer", diff_fields=("decision", "topic"),
          # A human decision that permanently overrides the AI for that topic. Nothing recorded who.
          template="{actor} approved an answer for {target}"),

    # Privacy operations, including the log's own.
    _spec(SUBJECT_ERASED, PRIVACY, "subject", durability=CRITICAL,
          diff_fields=("rows_pseudonymised", "request_ref"),
          template="{actor} erased subject data"),
    _spec(AUDIT_EXPORTED, PRIVACY, "audit_log", diff_fields=("row_count", "filters"),
          # Auditing reads of the audit log is a standard tender question.
          template="{actor} exported the audit log"),
)

REGISTRY: dict[str, ActionSpec] = {spec.action: spec for spec in _SPECS}
ACTIONS = frozenset(REGISTRY)


def spec_for(action: str) -> ActionSpec:
    try:
        return REGISTRY[action]
    except KeyError:  # pragma: no cover - a programming error, surfaced loudly by the tests
        raise KeyError(f"unregistered audit action: {action}") from None


def readable_categories(can: object) -> set[str]:
    """Categories a caller may read in full, given a capability predicate."""
    return {spec.category for spec in _SPECS
            if spec.read_capability is None or can(spec.read_capability)}


def unreadable_actions(can) -> list[str]:
    """Actions the caller must not see. Applied in SQL, not after the LIMIT.

    Filtering after the page is fetched silently returns short pages and, once paging exists, skips
    rows entirely. It is also the difference between "you cannot read this" and "you can tell how many
    of these exist", which for spend caps is the disclosure the gate was protecting.
    """
    return [spec.action for spec in _SPECS
            if spec.read_capability is not None and not can(spec.read_capability)]
