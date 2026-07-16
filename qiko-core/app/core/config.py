"""Typed application settings. No inline os.getenv elsewhere in the app.

Secrets come from the environment locally and from AWS SSM per environment in the cloud;
this class is the single place that reads them.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    dev = "dev"
    preprod = "preprod"
    live = "live"


# The forgeable local default for `session_secret`. A non-dev deploy must never run on it (any
# holder of this value could mint valid session tokens) -- enforced by Settings.assert_secrets_set.
DEFAULT_SESSION_SECRET = "change-me-locally"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = Environment.dev
    log_level: str = "INFO"

    # Data
    database_url: str = "postgresql+asyncpg://qiko:change-me-locally@db:5432/qiko"
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
    aws_region: str = "eu-central-1"
    bedrock_inference_profile: str = "eu"  # eu | us | jp | au | global | "" (in-region)
    bedrock_model: str = "anthropic.claude-sonnet-4-5"
    embeddings_provider: str = "local"
    embeddings_dim: int = 1024

    # Integrations. Empty = dev/stub; set per environment via SSM. Never commit real values.
    stripe_webhook_secret: str = ""
    stripe_secret_key: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""   # HMAC secret for inbound webhook signature verification
    slack_bot_token: str = ""
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_redirect_uri: str = ""
    slack_scopes: str = "chat:write,channels:read,im:history,commands"
    clickup_api_token: str = ""
    calendly_token: str = ""
    signal_engine_url: str = ""
    signal_engine_api_key: str = ""
    ga4_property_id: str = ""
    ga4_access_token: str = ""
    voice_model: str = "amazon.nova-sonic-v1:0"

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
    public_base_url: str = "http://localhost:3000"
    # Share the auth/CSRF cookies across subdomains (e.g. ".preprod.qiko.ai" so both
    # preprod.qiko.ai and admin.preprod.qiko.ai see the same session). Empty = host-only
    # cookie (dev default; fine when creator/admin/API are all on the same host).
    cookie_domain: str = ""

    # Email
    email_backend: str = "console"  # console | smtp
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "no-reply@qiko.ai"
    labs_contact_email: str = "support@qiko.ai"

    # API hardening
    cors_allow_origins: list[str] = ["http://localhost:3000"]
    rate_limit_per_minute: int = 120
    # /auth/login is a credential-stuffing/brute-force target -- the generic per-path limit above
    # (120/min) is far too permissive for it specifically, so it gets its own much tighter budget.
    auth_rate_limit_per_minute: int = 10
    max_request_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Auth
    session_secret: str = DEFAULT_SESSION_SECRET
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1209600

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.live

    @property
    def debug(self) -> bool:
        """Only dev exposes debug affordances (docs, verbose errors)."""
        return self.environment is Environment.dev

    def assert_secrets_set(self) -> None:
        """Fail closed: a non-dev deploy must refuse to start on the forgeable default
        session_secret, so production can never silently sign/verify tokens with a known key."""
        if self.environment is not Environment.dev and self.session_secret == DEFAULT_SESSION_SECRET:
            raise RuntimeError(
                "session_secret is still the insecure default; set SESSION_SECRET before starting "
                f"in a non-dev environment (environment={self.environment.value})")


@lru_cache
def get_settings() -> Settings:
    return Settings()
