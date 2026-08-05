"""FastAPI application entry point for qiko-core.

Modular monolith: each domain lives under app/modules/<name> and registers its own router here.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.core.db import build_engine, build_sessionmaker, build_sync_engine, build_sync_sessionmaker
from app.core.config import Environment, get_settings
from app.core.deps import WorkerUnavailable
from app.modules.chat.service import ConversationScopeError
from app.modules.workers.worker import StubProviderUnavailable
from app.core.logging import configure_logging
from app.core.middleware import (
    AiUsageMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.observability import RequestContextMiddleware
from app.core.ratelimit import InMemoryRateLimiter, RedisRateLimiter
from app.core.redis import build_redis
from app.core.dev_gateways import (
    StubGA4Gateway,
    StubSignalEngine,
    StubSpeechGateway,
    StubStripeGateway,
    StubWhatsAppGateway,
)
from app.core.observability import init_sentry, init_tracing
from app.integrations.clients import (
    GA4Client,
    SignalEngineClient,
    StripeClient,
    WhatsAppClient,
)
from app.modules.billing.payment_links import PaymentLinkService
from app.modules.channels.sessions import ChannelSessionStore
from app.modules.channels.slack_oauth import InstallationStore, SlackOAuth, WorkspaceLinkStore
from app.modules.channels.teams_integration import TeamsNotifier
from app.modules.chat.files import FileGenerator
from app.modules.identity.admin_rbac import AdminOrg
from app.modules.identity.onboarding import OtpStore
from app.modules.identity.pending_signup import InMemoryPendingSignupStore
from app.tasks.jobs import registry as task_registry
from app.tasks.queue import get_task_queue as build_task_queue
from app.modules.admin.customers import CustomerDirectory
from app.modules.signal.router import router as signal_router
from app.core.tenancy import tenant_dependency
from app.modules.admin.router import router as admin_router
from app.modules.agents.router import router as agents_router
from app.modules.agents.service import AgentService
from app.modules.ai.caps import CostCapExceeded, CostGuard, InMemoryCostCapStore
from app.modules.ai.usage import InMemoryUsageStore
from app.modules.assignments.router import router as assignments_router
from app.modules.assignments.service import AssignmentService
from app.modules.rfp.router import router as rfp_router
from app.modules.rfp.service import PackAnswerService, RequirementService, RfpPackService
from app.modules.rfp.tree import PackTreeService
from app.modules.billing.router import router as billing_router
from app.modules.billing.subscriptions import SubscriptionService
from app.modules.billing.webhook import StripeWebhookHandler
from app.modules.channels.router import router as channels_router
from app.modules.channels.whatsapp import WhatsAppAdapter
from app.modules.chat.public_router import router as public_chat_router
from app.modules.chat.router import router as chat_router
from app.modules.chat.service import ChatService
from app.modules.consent.router import router as consent_router
from app.modules.consent.service import ConsentService
from app.modules.crm.router import router as crm_router
from app.modules.crm.service import CrmService
from app.modules.notifications.router import router as notifications_router
from app.modules.notifications.service import NotificationService
from app.modules.sales_intelligence.notifications import SalesNotificationService
from app.modules.sales_intelligence.router import router as sales_intelligence_router
from app.modules.sales_intelligence.salesforce import SalesforceAuthService, SalesforcePushService
from app.modules.sales_intelligence.service import OpportunityMutationService, OpportunityService
from app.modules.agentcore.batch_router import router as batch_router
from app.modules.excel.router import router as excel_router
from app.modules.excel.service import ExcelService
from app.modules.finance.router import router as finance_router
from app.modules.finance.service import FinanceService
from app.modules.health.router import router as health_router
from app.modules.identity.admin_org_router import router as admin_org_router
from app.modules.identity.onboarding_router import router as onboarding_router
from app.modules.identity.router import router as identity_router
from app.modules.identity.team_access import PendingInviteStore
from app.modules.identity.users_router import router as identity_users_router
from app.modules.identity.twofa_router import router as twofa_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.sources import KnowledgeSources
from app.modules.knowledge.sources_router import router as sources_router
from app.modules.leads.router import router as leads_router
from app.modules.leads.service import LeadService
from app.modules.marketing.router import router as marketing_router
from app.modules.teams.router import router as teams_router
from app.modules.teams.service import TeamService
from app.modules.voice.pipeline import SpeechUnavailable, UnavailableSpeechGateway, VoicePipeline
from app.modules.voice.router import router as voice_router
from app.modules.email.sender import get_email_sender


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail closed before serving any request: a non-dev deploy must never run on the forgeable
    # default session_secret, nor on the in-memory stores / inline task backend (see
    # Settings.assert_secrets_set).
    get_settings().assert_secrets_set()
    # Build the async engine + sessionmaker (lazy connect) so DB-backed stores can be wired.
    engine = build_engine()
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    app.state.sync_engine = None
    if get_settings().use_db_stores:
        # Flip the live app from in-memory to the Postgres-backed stores (async end-to-end).
        from app.db.stores import (
            SqlActionStore,
            SqlActivityLogStore,
            SqlAdminOrgStore,
            SqlAgentStore,
            SqlAssignmentStore,
            SqlChatStore,
            SqlConsentStore,
            SqlContactStore,
            SqlFinanceChatStore,
            SqlFinanceFileStore,
            SqlIngestFilterSettingStore,
            SqlIngestionSourceStore,
            SqlLeadStore,
            SqlNotificationStore,
            SqlOpportunityStore,
            SqlOtpStore,
            SqlPackAnswerStore,
            SqlPackQuestionStore,
            SqlPackSectionStore,
            SqlPendingInviteStore,
            SqlPendingSignupStore,
            SqlRequirementStore,
            SqlRfpPackStore,
            SqlSalesforceConnectionStore,
            SqlTeamsIntegrationStore,
            SqlTeamStore,
            SqlCostCapStore,
            SqlUsageStore,
            SqlUserStore,
            SqlVectorStore,
        )
        from app.modules.identity.router import set_store as set_user_store

        sm = app.state.sessionmaker
        app.state.knowledge = KnowledgeService(store=SqlVectorStore(sm))
        app.state.excel = ExcelService(app.state.knowledge)
        app.state.sources = KnowledgeSources(app.state.knowledge)
        app.state.chat = ChatService(store=SqlChatStore(sm))
        app.state.crm = CrmService(app.state.chat, contacts=SqlContactStore(sm), actions=SqlActionStore(sm))
        # Sales Intelligence: opportunities/sources/activity + Salesforce connections survive a
        # redeploy. The mutation service and Salesforce services share the same DB-backed stores
        # so all four API surfaces read/write one source of truth (Salesforce tokens stay
        # Fernet-encrypted at rest via app.core.crypto -- see SqlSalesforceConnectionStore).
        si_sources = SqlIngestionSourceStore(sm)
        si_opportunities = SqlOpportunityStore(sm)
        si_activity_logs = SqlActivityLogStore(sm)
        si_connections = SqlSalesforceConnectionStore(sm)
        # Generic in-app notification inbox (reusable across verticals) + the SI trigger wrapper
        # that the scan/review/assign/push flows call. In-product only (no email/FCM push).
        app.state.ai_usage = SqlUsageStore(sm)  # AI spend survives a redeploy
        app.state.cost_caps = SqlCostCapStore(sm)
        app.state.cost_guard = CostGuard(caps=app.state.cost_caps, usage=app.state.ai_usage)
        app.state.notifications = NotificationService(store=SqlNotificationStore(sm))
        app.state.cost_guard.notifications = app.state.notifications
        sales_notifier = SalesNotificationService(notifications=app.state.notifications)
        app.state.sales_notifier = sales_notifier
        app.state.sales_intel = OpportunityService(
            scan_interval_minutes=get_settings().idg_sales_scan_interval_minutes,
            sources=si_sources, opportunities=si_opportunities, activity_logs=si_activity_logs,
            notifier=sales_notifier)
        app.state.sales_intel_mutation = OpportunityMutationService(
            opportunities=si_opportunities, activity_logs=si_activity_logs, notifier=sales_notifier)
        app.state.sales_intel_ingest_filters = SqlIngestFilterSettingStore(sm)
        app.state.salesforce_auth = SalesforceAuthService(
            connections=si_connections, activity_logs=si_activity_logs)
        app.state.salesforce_push = SalesforcePushService(
            auth=app.state.salesforce_auth, activity_logs=si_activity_logs, notifier=sales_notifier,
            opportunities=si_opportunities)
        # Finance vertical: uploaded workbooks (parsed rows) + analyst chat history survive a
        # redeploy. The LLM provider is the same configured gateway used elsewhere.
        app.state.finance = FinanceService(files=SqlFinanceFileStore(sm), chats=SqlFinanceChatStore(sm))
        app.state.agents = AgentService(store=SqlAgentStore(sm))  # workers survive a redeploy
        app.state.rfp_packs = RfpPackService(store=SqlRfpPackStore(sm))
        app.state.requirements = RequirementService(store=SqlRequirementStore(sm))
        app.state.pack_answers = PackAnswerService(store=SqlPackAnswerStore(sm))
        app.state.pack_tree = PackTreeService(sections=SqlPackSectionStore(sm), questions=SqlPackQuestionStore(sm))
        app.state.assignments = AssignmentService(store=SqlAssignmentStore(sm))
        app.state.admin_org = AdminOrg(store=SqlAdminOrgStore(sm))  # platform admins survive a redeploy
        app.state.teams = TeamService(store=SqlTeamStore(sm))  # teams/membership survive a redeploy
        app.state.leads = LeadService(get_email_sender(), store=SqlLeadStore(sm))  # leads survive a redeploy
        app.state.teams_notifier = TeamsNotifier(store=SqlTeamsIntegrationStore(sm))  # webhook survives a redeploy
        # Password-reset codes + pending team invites survive a redeploy and are shared across
        # processes (previously in-memory, so a code/invite could silently stop working).
        app.state.otp_store = SqlOtpStore(sm)
        app.state.pending_invites = SqlPendingInviteStore(sm)
        app.state.pending_signups = SqlPendingSignupStore(sm)
        app.state.consent = ConsentService(store=SqlConsentStore(sm))
        set_user_store(SqlUserStore(sm))  # users/sessions/2FA persist to Postgres

        # Billing state + the admin Customers console are reached through SYNCHRONOUS route
        # handlers (FastAPI runs those in a threadpool), so they use a synchronous engine (see
        # app.db.sync_stores). Swapping these in makes subscriptions/invoices/payment-links
        # durable and derives the admin customer list from the real tenants -- previously all of
        # these lived only in process memory and were wiped on every restart.
        from app.db.sync_stores import (
            SqlCustomerDirectory,
            SqlInvoiceStore,
            SqlPaymentLinkStore,
            SqlSubscriptionStore,
        )

        sync_engine = build_sync_engine()
        app.state.sync_engine = sync_engine
        sync_sm = build_sync_sessionmaker(sync_engine)
        # Keep the already-selected Stripe gateway + email sender (stub until real keys are set);
        # only the STATE backend changes from in-memory to Postgres.
        stripe_gateway = app.state.subscriptions.gateway
        app.state.subscriptions = SubscriptionService(stripe_gateway, store=SqlSubscriptionStore(sync_sm))
        app.state.stripe_webhook = StripeWebhookHandler(
            invoices=SqlInvoiceStore(sync_sm), subscriptions=app.state.subscriptions)
        app.state.payment_links = PaymentLinkService(
            gateway=app.state.payment_links.gateway, email=app.state.payment_links.email,
            store=SqlPaymentLinkStore(sync_sm))
        app.state.customers = SqlCustomerDirectory(sync_sm)
    try:
        yield
    finally:
        await engine.dispose()
        if app.state.sync_engine is not None:
            app.state.sync_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Qiko Core",
        version=__version__,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.exception_handler(CostCapExceeded)
    async def cost_cap_handler(_request: Request, exc: CostCapExceeded) -> JSONResponse:
        """A reached cap is a business condition, not a server fault.

        402 rather than 429: the request is not rate limited and retrying will not help until either
        the cap is raised or the month rolls over, and a 500 would send an operator hunting a bug that
        does not exist. The body says how much of the cap is used so the message a customer sees can be
        specific.
        """
        decision = exc.decision
        return JSONResponse(status_code=402, content={
            "detail": "AI spend cap reached for this month",
            "spent_nano_usd": decision.spent_nano_usd,
            "limit_nano_usd": decision.limit_nano_usd,
            "used_pct": decision.used_pct,
        })

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        """Never echo the submitted value back.

        FastAPI's default 422 body is `exc.errors()`, and each Pydantic v2 error carries an `input`
        key. For a `missing` error that `input` is the WHOLE enclosing object, not just the offending
        field -- so omitting one required field would return every other field, including plaintext
        passwords on /auth/login, /auth/signup, /auth/reset-password and the integration secrets on
        the *-credentials endpoints. We keep loc/type/msg so clients still know what failed.
        """
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": [str(part) for part in err.get("loc", ())],
             "type": err.get("type", ""),
             "msg": err.get("msg", "")}
            for err in error.errors()
        ]})

    @app.exception_handler(WorkerUnavailable)
    async def worker_unavailable_handler(
        _request: Request, _error: WorkerUnavailable
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "worker not found"})

    @app.exception_handler(ConversationScopeError)
    async def conversation_scope_handler(
        _request: Request, _error: ConversationScopeError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "worker not found"})

    @app.exception_handler(SpeechUnavailable)
    async def speech_unavailable_handler(
        _request: Request, _error: SpeechUnavailable
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": "voice service is temporarily unavailable"})

    @app.exception_handler(StubProviderUnavailable)
    async def stub_provider_unavailable_handler(
        _request: Request, _error: StubProviderUnavailable
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "answer generation is temporarily unavailable"},
        )

    # Observability exporters (no-ops unless configured for the environment).
    init_sentry()
    if settings.otel_enabled:
        init_tracing(app)

    # API hardening (outermost first): request-id correlation, security headers, size cap, rate limit, CORS.
    app.add_middleware(AiUsageMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    if settings.environment is Environment.dev:
        limiter = InMemoryRateLimiter(limit=settings.rate_limit_per_minute)
        strict_limiter = InMemoryRateLimiter(limit=settings.auth_rate_limit_per_minute)
        # None means "not configured": in dev the limiter is in-memory, so the readiness probe must
        # report not-configured rather than failing.
        app.state.redis = None
    else:
        redis = build_redis(settings.redis_url)
        # Exposed so the readiness probe and the system dashboard can reach the same client the rate
        # limiter uses, rather than opening a second connection to answer "is Redis up".
        app.state.redis = redis
        limiter = RedisRateLimiter(redis=redis, namespace="qiko:rate", limit=settings.rate_limit_per_minute)
        strict_limiter = RedisRateLimiter(
            redis=redis, namespace="qiko:strict-rate", limit=settings.auth_rate_limit_per_minute)
    app.add_middleware(RateLimitMiddleware,
                       limiter=limiter,
                       strict_limiter=strict_limiter,
                       strict_paths=("/api/v1/auth/login", "/api/v1/auth/refresh",
                                    "/api/v1/auth/2fa", "/api/v1/auth/signup",
                                    "/api/v1/auth/verify-email", "/api/v1/auth/forgot-password",
                                    "/api/v1/auth/reset-password", "/api/v1/consent",
                                    # unauthenticated and sends mail to a human inbox: 120/min/IP
                                    # was enough to flood it and burn sending reputation.
                                    "/api/v1/marketing/labs-contact"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Domain service singletons (in-memory dev defaults; DB-backed stores swap in behind the same
    # protocols in SCRUM-57. External gateways use the real client (app/integrations/clients.py)
    # when the matching secret is configured, dev stub otherwise -- see the selector block below).
    app.state.knowledge = KnowledgeService()
    app.state.agents = AgentService()
    app.state.rfp_packs = RfpPackService()
    app.state.requirements = RequirementService()
    app.state.pack_answers = PackAnswerService()
    app.state.pack_tree = PackTreeService()
    app.state.assignments = AssignmentService()
    app.state.chat = ChatService()
    app.state.crm = CrmService(app.state.chat)
    # Generic in-app notification inbox (reusable across verticals) + the SI trigger wrapper.
    app.state.ai_usage = InMemoryUsageStore()
    app.state.cost_caps = InMemoryCostCapStore()
    # A guard IS attached, over the in-memory stores, so the enforcement path is exercised by the
    # test suite rather than existing only in production.
    app.state.cost_guard = CostGuard(caps=app.state.cost_caps, usage=app.state.ai_usage)
    app.state.notifications = NotificationService()
    app.state.cost_guard.notifications = app.state.notifications
    app.state.sales_notifier = SalesNotificationService(notifications=app.state.notifications)
    app.state.sales_intel = OpportunityService(scan_interval_minutes=settings.idg_sales_scan_interval_minutes,
                                               notifier=app.state.sales_notifier)
    app.state.sales_intel_mutation = OpportunityMutationService(opportunities=app.state.sales_intel.opportunities,
                                                                 activity_logs=app.state.sales_intel.activity_logs,
                                                                 notifier=app.state.sales_notifier)
    from app.modules.sales_intelligence.models import InMemoryIngestFilterSettingStore
    app.state.sales_intel_ingest_filters = InMemoryIngestFilterSettingStore()
    app.state.salesforce_auth = SalesforceAuthService()
    app.state.salesforce_push = SalesforcePushService(auth=app.state.salesforce_auth,
                                                      notifier=app.state.sales_notifier,
                                                      opportunities=app.state.sales_intel.opportunities)
    app.state.finance = FinanceService()
    app.state.teams = TeamService()
    app.state.leads = LeadService(get_email_sender())
    app.state.teams_notifier = TeamsNotifier()

    # Real client if the secret is configured, dev stub otherwise -- same pattern as
    # get_email_sender(). Speech (TTS/STT) has no real client yet, so it stays stubbed. The channel
    # integrations (Calendly, ClickUp, Slack, Gmail) are per-worker connections built per request
    # from the tenant's own encrypted credential, so they are deliberately NOT wired here.
    stripe_gateway = StripeClient() if settings.stripe_secret_key else StubStripeGateway()
    app.state.subscriptions = SubscriptionService(stripe_gateway)
    # Give the webhook the subscription service so checkout.session.completed can link the tenant
    # (from the session's client_reference_id) to its real Stripe customer id and activate.
    app.state.stripe_webhook = StripeWebhookHandler(subscriptions=app.state.subscriptions)
    app.state.whatsapp = WhatsAppAdapter(
        WhatsAppClient() if settings.whatsapp_access_token else StubWhatsAppGateway())
    app.state.excel = ExcelService(app.state.knowledge)
    app.state.sources = KnowledgeSources(app.state.knowledge)
    speech_gateway = StubSpeechGateway() if settings.debug else UnavailableSpeechGateway()
    app.state.voice = VoicePipeline(speech_gateway)
    app.state.signal_engine = SignalEngineClient() if settings.signal_engine_url else StubSignalEngine()
    app.state.customers = CustomerDirectory()
    app.state.ga4 = GA4Client() if settings.ga4_property_id and settings.ga4_access_token else StubGA4Gateway()
    app.state.payment_links = PaymentLinkService(gateway=stripe_gateway, email=get_email_sender())
    app.state.admin_org = AdminOrg()
    app.state.otp_store = OtpStore()
    app.state.pending_invites = PendingInviteStore()
    app.state.pending_signups = InMemoryPendingSignupStore()
    app.state.consent = ConsentService()
    app.state.channel_sessions = ChannelSessionStore()
    app.state.slack_oauth = SlackOAuth(InstallationStore())
    app.state.slack_links = WorkspaceLinkStore()
    app.state.file_generator = FileGenerator()
    app.state.task_queue = build_task_queue(task_registry)

    # Every request is tenant-scoped.
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api/v1", dependencies=[Depends(tenant_dependency)])
    for r in (identity_router, identity_users_router, knowledge_router, agents_router, rfp_router,
              assignments_router, admin_router, chat_router, teams_router, leads_router, billing_router,
              channels_router, excel_router, voice_router, signal_router, public_chat_router, sources_router,
              twofa_router, onboarding_router, admin_org_router, batch_router, marketing_router, crm_router,
              sales_intelligence_router, finance_router, notifications_router, consent_router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
