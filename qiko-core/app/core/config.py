"""Typed application settings. No inline os.getenv elsewhere in the app.

Secrets come from the environment locally and from AWS SSM per environment in the cloud;
this class is the single place that reads them.
"""
from __future__ import annotations

import ipaddress
from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    dev = "dev"
    preprod = "preprod"
    live = "live"


# The forgeable local default for `session_secret`. A non-dev deploy must never run on it (any
# holder of this value could mint valid session tokens) -- enforced by Settings.assert_secrets_set.
DEFAULT_SESSION_SECRET = "cha" + "nge-me-locally"


def _strong_secret(value: str) -> bool:
    lowered = value.lower()
    return (len(value) >= 32 and len(set(value)) >= 8
            and "change-me" not in lowered and "replace" not in lowered)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = Environment.dev
    log_level: str = "INFO"

    # Data
    database_url: str = "postgresql+asyncpg://qiko:" + "change-me-locally" + "@db:5432/qiko"
    # A second connection for the audit maintenance role, WORKER-ONLY. Once migration 0039 has revoked
    # UPDATE and DELETE on audit_events from the application role, retention and erasure can only run
    # through this one. Empty means the boundary is not in force yet and the jobs use the ordinary URL,
    # which is what makes the two changes independently deployable.
    #
    # Deliberately never read by the API process: the point of the split is that a request handler
    # cannot reach a connection able to rewrite history, and a setting the API never loads cannot be
    # reached by accident.
    audit_maint_database_url: str = ""
    redis_url: str = "redis://redis:6379/0"
    task_backend: str = "eager"  # eager (dev/tests) | arq (prod worker tier)
    use_db_stores: bool = False  # True -> live app uses the Postgres-backed stores

    # Observability (exporters off by default; enabled per environment)
    sentry_dsn: str = ""
    otel_enabled: bool = False
    otel_exporter_endpoint: str = ""

    # AI gateway (ADR-007/008/009)
    ai_provider: str = "bedrock"
    ai_fallback_provider: str = "stub"
    # Read timeout for the per-answer hot path (see BedrockProvider.read_timeout). A setting rather
    # than a constant because the value that is right depends on how long the configured model
    # takes to reach the output ceiling, which is a property of the deployment, not of the code:
    # it was 20s, and a Sonnet 4.5 answer that runs to the full 1024-token ceiling measured 22-23s
    # against eu-central-1, so every long answer timed out and fell through to the stub provider.
    ai_read_timeout_seconds: int = 45
    aws_region: str = "eu-central-1"
    bedrock_inference_profile: str = "eu"  # eu | us | jp | au | global | "" (in-region)
    bedrock_model: str = "anthropic.claude-sonnet-4-5"
    # Cheap/fast tier for narrow, single-facet work with many parallel calls per pipeline run (the
    # agentic pipeline's Specialist role - see app.tasks.jobs._build_idg_pipeline_deps and
    # _build_pipeline_deps). Synthesizer/Critic keep the capable bedrock_model tier above: fewer
    # calls per run, and both are consolidation/judgment roles where the cascade-routing
    # literature (e.g. "A Unified Approach to Routing and Cascading for LLMs", ICML 2025) treats
    # quality as mattering more than for narrow per-item work.
    bedrock_model_fast: str = "anthropic.claude-haiku-4-5"
    # Generated file storage. Empty means the in-memory backend, which is a plain dict with no TTL
    # and no eviction: acceptable in dev, an unbounded leak plus data loss on restart in production.
    s3_bucket: str = ""
    embeddings_provider: str = "local"
    embeddings_dim: int = 1024

    # Integrations. Empty = dev/stub; set per environment via SSM. Never commit real values.
    stripe_webhook_secret: str = ""
    stripe_secret_key: str = ""
    # Real Stripe recurring price ID for the self-serve Premium ("pro") plan. Empty => self-serve
    # checkout is unavailable (endpoint returns a clear 503) until provisioned in SSM. Enterprise is
    # contact-sales and free is a trial, so neither is self-serve checkout.
    stripe_price_pro: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""   # HMAC secret for inbound webhook signature verification
    interakt_webhook_secret: str = ""   # HMAC secret for Interakt's Interakt-Signature header
    interakt_api_key: str = ""   # Template Message Send API auth
    # jm-backend's internal API (JM2-1023): investor lookup + WhatsApp conversation persistence.
    jm_backend_base_url: str = ""
    jm_backend_shared_secret: str = ""
    # The reverse direction (JM2-1065/1066): jm-backend calling INTO qiko-core's worker API.
    jm_backend_api_key: str = ""
    # JM2-1131: investor activity tracking + intent signals. Mobile syncs directly to qiko-core
    # (not through jm-backend), authenticated with a short-lived token minted by whichever
    # investor-facing backend a client runs (jm-backend, joseph-mews-backend, or a future
    # equivalent) and verified here statelessly (no round trip per activity event). Deliberately
    # its own secret, not session_secret or jm_backend_shared_secret: different trust boundary,
    # and named generically so it is not tied to one specific backend's identity.
    investor_activity_token_secret: str = ""
    investor_activity_token_ttl_seconds: int = 24 * 60 * 60
    # JM2-1134: how long an investor must be quiet before their activity is drafted into intent
    # signals. A browsing session emits many events, so drafting on the first would describe a
    # half-finished visit and then be replaced minutes later, paying for both.
    jm_signal_draft_delay_minutes: int = 10
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""   # Slack request signing for the inbound Events API
    slack_redirect_uri: str = ""
    # Least privilege for the heads-up assistant: PUBLIC channel history only. groups:history
    # (private channels) and im:history (DMs) are deliberately NOT requested -- the handler drops
    # anything that is not a public channel, so asking for them would grant standing read access to
    # conversations the feature never looks at and widen the blast radius if the token leaked.
    # `commands` is NOT requested: no slash-command handler exists in qiko-core, so it would be a
    # scope granted for a surface that does not ship.
    slack_scopes: str = "channels:history,channels:read,app_mentions:read,chat:write"
    slack_digest_interval_minutes: int = 60
    slack_message_retention_days: int = 7
    signal_engine_url: str = ""
    signal_engine_api_key: str = ""
    ga4_property_id: str = ""
    ga4_access_token: str = ""
    voice_model: str = "amazon.nova-sonic-v1:0"

    # Qiko Track integration. Base URL is per-worker and is allowlisted for SSRF/API7 protection.
    qiko_track_api_base: str = "https://track.qiko.ai"
    qiko_track_api_allowlist: list[str] = ["https://track.qiko.ai"]
    # Service token for one-click Qiko Track auto-connect. Empty keeps the manual token form.
    qiko_track_service_token: str = ""

    # GitHub App (read-only connector). Empty means GitHub App install flow is unavailable.
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_app_slug: str = ""
    github_app_webhook_secret: str = ""
    github_api_base: str = "https://api.github.com"
    github_api_allowlist: list[str] = ["https://api.github.com"]

    # Salesforce OAuth (authorization_code + PKCE, matching the real IDG Sales Salesforce
    # Connected App flow -- NOT the client_credentials shape used by app.integrations.clients.
    # SalesforceClient/app.modules.crm's generic per-worker connection; see
    # app.modules.sales_intelligence.salesforce for the authorization_code implementation).
    salesforce_client_id: str = ""
    salesforce_client_secret: str = ""
    salesforce_redirect_uri: str = ""
    salesforce_login_base_url: str = "https://login.salesforce.com"
    salesforce_scopes: str = "api refresh_token offline_access"
    salesforce_api_version: str = "v59.0"
    salesforce_default_stage_name: str = "Prospecting"
    salesforce_external_id_field: str = ""
    salesforce_frontend_success_path: str = "/app/studio/{agentId}"
    frontend_url: str = "http://127.0.0.1:5173"

    # IDG Sales Intelligence (app.modules.sales_intelligence)
    idg_sales_scan_interval_minutes: int = 1
    # Minimum time between two agentic-pipeline enqueues for the same opportunity (QIW cost
    # incident, 2026-09-14). See OpportunityService._may_enqueue_pipeline.
    idg_pipeline_reenqueue_cooldown_minutes: int = 60
    # Total agentic-pipeline runs a single opportunity may ever accrue. The cooldown above only
    # bounds the RATE for one opportunity; an opportunity that never resolves (stays
    # awaiting_review forever) still got a fresh run every cooldown window, unbounded, so the
    # tenant's total Bedrock spend kept climbing even after the 2026-09-14 fix (QIW cost incident
    # continuation, 2026-09-16). None means unlimited. See OpportunityService._may_enqueue_pipeline.
    idg_pipeline_max_attempts: int | None = 3
    public_base_url: str = "http://localhost:3000"
    # Public/embed chat is disabled by default for enterprise deployments. Dev keeps it available for
    # local tests; non-dev must opt in explicitly.
    public_chat_enabled: bool = False
    # WhatsApp inbound is receive-and-discard: the adapter de-duplicates and returns ids without
    # resolving a worker, generating an answer or replying. Off by default so the platform does not
    # advertise a capability it does not have (QIK audit H9).
    channels_inbound_enabled: bool = False
    # Share the auth/CSRF cookies across subdomains (e.g. ".preprod.qiko.ai" so both
    # preprod.qiko.ai and admin.preprod.qiko.ai see the same session). Empty = host-only
    # cookie (dev default; fine when creator/admin/API are all on the same host).
    cookie_domain: str = ""
    legacy_cookie_domain: str = ""

    # Email
    email_backend: str = "console"  # console | smtp
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_timeout_seconds: int = 10
    email_from: str = "no-reply" + "@" + "qiko.ai"
    labs_contact_email: str = "support" + "@" + "qiko.ai"
    contact_inbox: str = "contact" + "@" + "qiko.ai"

    # API hardening
    # First-party origins. Two separate powers, not one: browsers there may read our responses,
    # AND require_csrf accepts them as the Origin of a cookie-authenticated mutation. Only put a
    # Qiko-operated origin here.
    cors_allow_origins: list[str] = ["http://localhost:3000"]
    # Third-party origins that may read responses in a browser and are deliberately NOT trusted
    # for cookie-authenticated mutations (QIKO-1102). Kept apart from cors_allow_origins because
    # that list is also require_csrf's trusted-origin list: adding an integrator there to clear a
    # CORS error would also make their origin acceptable for login refresh, logout, 2FA, consent
    # and every admin and billing mutation, which is far more than the CORS request asked for.
    # Nothing added here can grant that, by construction rather than by review.
    partner_cors_origins: list[str] = []
    rate_limit_per_minute: int = 120
    # /auth/login is a credential-stuffing/brute-force target -- the generic per-path limit above
    # (120/min) is far too permissive for it specifically, so it gets its own much tighter budget.
    auth_rate_limit_per_minute: int = 10
    max_request_bytes: int = 10 * 1024 * 1024  # 10 MB
    forwarded_allow_ips: str = "127.0.0.1"

    # Auth
    session_secret: str = DEFAULT_SESSION_SECRET
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1209600

    # Dedicated key for encryption-at-rest (channel tokens, Vapi/Salesforce secrets). Kept SEPARATE
    # from session_secret so the two rotate independently -- rotating SESSION_SECRET must never brick
    # already-encrypted secrets. Empty -> legacy behaviour (key derived from session_secret); see
    # app.core.crypto, which falls back to the legacy key for decryption so old ciphertext survives.
    encryption_key: str = ""
    consent_pseudonym_keys: dict[str, str] = Field(default_factory=dict)
    consent_pseudonym_active_version: str = "v1"

    @property
    def browser_allowed_origins(self) -> list[str]:
        """Every origin CORSMiddleware accepts: first-party plus partner. This is the CORS
        question only. The CSRF trust question is answered by cors_allow_origins alone, and
        keeping the two reads distinct is the whole point of the split."""
        seen: dict[str, None] = {}
        for origin in (*self.cors_allow_origins, *self.partner_cors_origins):
            # Dedup preserving order: CORSMiddleware matches the Origin header by exact string,
            # so a repeat is harmless, but the resulting config is easier to read without it.
            seen.setdefault(origin, None)
        return list(seen)

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.live

    @property
    def debug(self) -> bool:
        """Only dev exposes debug affordances (docs, verbose errors)."""
        return self.environment is Environment.dev

    def assert_secrets_set(self) -> None:
        """Fail closed before serving traffic in a non-dev environment.

        1. Refuse to start on the forgeable default session_secret, so production can never
           silently sign/verify tokens with a known key.
        2. Refuse to start on the in-memory / inline defaults (use_db_stores=False,
           task_backend="eager"). Those are dev/test conveniences: on a live deploy they would
           silently drop all data on every restart and run the 30-min generation inline (hitting
           the load-balancer timeout). A misconfigured deploy that forgets USE_DB_STORES=true /
           TASK_BACKEND=arq must crash loudly, not degrade silently.

        dev is unaffected on all counts.
        """
        if self.environment is Environment.dev:
            return
        misconfigured = []
        if not _strong_secret(self.session_secret):
            misconfigured.append("SESSION_SECRET with at least 32 non-placeholder characters")
        if not _strong_secret(self.encryption_key) or self.encryption_key == self.session_secret:
            misconfigured.append("a distinct ENCRYPTION_KEY with at least 32 non-placeholder characters")
        if self.use_db_stores is not True:
            misconfigured.append("USE_DB_STORES=true (persistent Postgres-backed stores)")
        if self.task_backend != "arq":
            misconfigured.append("TASK_BACKEND=arq (out-of-band worker tier)")
        active_consent_key = self.consent_pseudonym_keys.get(self.consent_pseudonym_active_version, "")
        if (not _strong_secret(active_consent_key)
                or any(not _strong_secret(key) for key in self.consent_pseudonym_keys.values())):
            misconfigured.append("CONSENT_PSEUDONYM_KEYS with strong active and retained keys")
        trusted_proxies = {value.strip() for value in self.forwarded_allow_ips.split(",") if value.strip()}
        valid_proxy_networks = []
        invalid_proxy = not trusted_proxies or "*" in trusted_proxies
        for value in trusted_proxies - {"*"}:
            try:
                network = ipaddress.ip_network(value, strict=False)
                valid_proxy_networks.append(network)
                invalid_proxy = invalid_proxy or network.prefixlen == 0
            except ValueError:
                invalid_proxy = True
        loopback_only = valid_proxy_networks and all(network.is_loopback for network in valid_proxy_networks)
        if invalid_proxy or loopback_only:
            misconfigured.append("FORWARDED_ALLOW_IPS with the trusted proxy addresses only")
        if self.email_backend != "smtp":
            misconfigured.append("EMAIL_BACKEND=smtp for deliverable verification email")
        if (not self.smtp_host or self.smtp_host in {"localhost", "127.0.0.1"}
                or not self.smtp_user or not self.smtp_password
                or "replace" in self.email_from.lower() or "@" not in self.email_from):
            misconfigured.append("complete non-placeholder SMTP host, credentials and sender")
        # Settings that default to a DEV value and degrade the product SILENTLY if the real
        # environment omits them. Everything above fails closed already; these did not.
        if not self.s3_bucket:
            # Every generated DOCX/XLSX/PDF/CSV would otherwise live in a process dict that grows
            # forever and is lost on every deploy, so previously issued download links 404.
            misconfigured.append("S3_BUCKET so generated files survive a restart and do not leak memory")
        if self.embeddings_provider == "local":
            # LocalEmbeddings is a SHA-256 bag-of-words hash into buckets, not a semantic model, so
            # RAG retrieval quietly becomes keyword hashing with no error and no health signal.
            misconfigured.append("EMBEDDINGS_PROVIDER=titan (the default 'local' is a dev-only hash embedder)")
        for label, url in (("PUBLIC_BASE_URL", self.public_base_url), ("FRONTEND_URL", self.frontend_url)):
            # public_base_url is baked into every verification / reset / welcome email link, so a
            # leftover localhost silently breaks signup for real users with no server-side error.
            if "localhost" in url or "127.0.0.1" in url:
                misconfigured.append(f"{label} pointing at the real host, not localhost")
        if any(not origin.startswith("https://") for origin in self.cors_allow_origins):
            # require_csrf validates the Origin header against this list, so a wrong entry 403s
            # login-refresh, logout, 2FA, consent and every admin mutation.
            misconfigured.append("CORS_ALLOW_ORIGINS with https:// origins only")
        if any(not origin.startswith("https://") for origin in self.partner_cors_origins):
            # Same rule, and it also rejects "*", which is invalid anyway next to
            # allow_credentials=True and would hand every site on the internet a readable
            # response from a partner-facing route.
            misconfigured.append("PARTNER_CORS_ORIGINS with https:// origins only")
        if misconfigured:
            raise RuntimeError(
                "unsafe production config: a non-dev deploy must not run on in-memory stores or "
                "the inline task backend (data is lost on restart and long jobs run inline). Set "
                f"{', '.join(misconfigured)} before starting (environment={self.environment.value})")


@lru_cache
def get_settings() -> Settings:
    return Settings()
