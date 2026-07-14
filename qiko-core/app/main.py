"""FastAPI application entry point for qiko-core.

Modular monolith: each domain lives under app/modules/<name> and registers its own router here.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.db import build_engine, build_sessionmaker
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.observability import RequestContextMiddleware
from app.core.ratelimit import InMemoryRateLimiter
from app.core.dev_gateways import (
    StubCalendlyGateway,
    StubClickUpGateway,
    StubGA4Gateway,
    StubGmailGateway,
    StubSignalEngine,
    StubSlackGateway,
    StubSpeechGateway,
    StubStripeGateway,
    StubWhatsAppGateway,
)
from app.core.observability import init_sentry, init_tracing
from app.integrations.clients import (
    CalendlyClient,
    ClickUpClient,
    GA4Client,
    SignalEngineClient,
    SlackClient,
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
from app.tasks.jobs import registry as task_registry
from app.tasks.queue import get_task_queue as build_task_queue
from app.modules.admin.customers import CustomerDirectory
from app.modules.signal.router import router as signal_router
from app.core.tenancy import tenant_dependency
from app.modules.admin.router import router as admin_router
from app.modules.agents.router import router as agents_router
from app.modules.agents.service import AgentService
from app.modules.assignments.router import router as assignments_router
from app.modules.assignments.service import AssignmentService
from app.modules.rfp.router import router as rfp_router
from app.modules.rfp.service import PackAnswerService, RequirementService, RfpPackService
from app.modules.billing.router import router as billing_router
from app.modules.billing.subscriptions import SubscriptionService
from app.modules.billing.webhook import StripeWebhookHandler
from app.modules.channels.router import router as channels_router
from app.modules.channels.whatsapp import WhatsAppAdapter
from app.modules.chat.public_router import router as public_chat_router
from app.modules.chat.router import router as chat_router
from app.modules.chat.service import ChatService
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
from app.modules.voice.pipeline import VoicePipeline
from app.modules.voice.router import router as voice_router
from app.modules.email.sender import get_email_sender


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the async engine + sessionmaker (lazy connect) so DB-backed stores can be wired.
    engine = build_engine()
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    if get_settings().use_db_stores:
        # Flip the live app from in-memory to the Postgres-backed stores (async end-to-end).
        from app.db.stores import (
            SqlActionStore,
            SqlActivityLogStore,
            SqlAdminOrgStore,
            SqlAgentStore,
            SqlAssignmentStore,
            SqlChatStore,
            SqlContactStore,
            SqlFinanceChatStore,
            SqlFinanceFileStore,
            SqlIngestionSourceStore,
            SqlLeadStore,
            SqlNotificationStore,
            SqlOpportunityStore,
            SqlPackAnswerStore,
            SqlRequirementStore,
            SqlRfpPackStore,
            SqlSalesforceConnectionStore,
            SqlTeamsIntegrationStore,
            SqlTeamStore,
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
        app.state.notifications = NotificationService(store=SqlNotificationStore(sm))
        sales_notifier = SalesNotificationService(notifications=app.state.notifications)
        app.state.sales_notifier = sales_notifier
        app.state.sales_intel = OpportunityService(
            scan_interval_minutes=get_settings().idg_sales_scan_interval_minutes,
            sources=si_sources, opportunities=si_opportunities, activity_logs=si_activity_logs,
            notifier=sales_notifier)
        app.state.sales_intel_mutation = OpportunityMutationService(
            opportunities=si_opportunities, activity_logs=si_activity_logs, notifier=sales_notifier)
        app.state.salesforce_auth = SalesforceAuthService(
            connections=si_connections, activity_logs=si_activity_logs)
        app.state.salesforce_push = SalesforcePushService(
            auth=app.state.salesforce_auth, activity_logs=si_activity_logs, notifier=sales_notifier)
        # Finance vertical: uploaded workbooks (parsed rows) + analyst chat history survive a
        # redeploy. The LLM provider is the same configured gateway used elsewhere.
        app.state.finance = FinanceService(files=SqlFinanceFileStore(sm), chats=SqlFinanceChatStore(sm))
        app.state.agents = AgentService(store=SqlAgentStore(sm))  # workers survive a redeploy
        app.state.rfp_packs = RfpPackService(store=SqlRfpPackStore(sm))
        app.state.requirements = RequirementService(store=SqlRequirementStore(sm))
        app.state.pack_answers = PackAnswerService(store=SqlPackAnswerStore(sm))
        app.state.assignments = AssignmentService(store=SqlAssignmentStore(sm))
        app.state.admin_org = AdminOrg(store=SqlAdminOrgStore(sm))  # platform admins survive a redeploy
        app.state.teams = TeamService(store=SqlTeamStore(sm))  # teams/membership survive a redeploy
        app.state.leads = LeadService(get_email_sender(), store=SqlLeadStore(sm))  # leads survive a redeploy
        app.state.teams_notifier = TeamsNotifier(store=SqlTeamsIntegrationStore(sm))  # webhook survives a redeploy
        set_user_store(SqlUserStore(sm))  # users/sessions/2FA persist to Postgres
    try:
        yield
    finally:
        await engine.dispose()


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

    # Observability exporters (no-ops unless configured for the environment).
    init_sentry()
    if settings.otel_enabled:
        init_tracing(app)

    # API hardening (outermost first): request-id correlation, security headers, size cap, rate limit, CORS.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RateLimitMiddleware,
                       limiter=InMemoryRateLimiter(limit=settings.rate_limit_per_minute),
                       strict_limiter=InMemoryRateLimiter(limit=settings.auth_rate_limit_per_minute),
                       strict_paths=("/api/v1/auth/login", "/api/v1/auth/refresh",
                                    "/api/v1/auth/2fa", "/api/v1/auth/signup",
                                    "/api/v1/auth/forgot-password", "/api/v1/auth/reset-password"))
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
    app.state.assignments = AssignmentService()
    app.state.chat = ChatService()
    app.state.crm = CrmService(app.state.chat)
    # Generic in-app notification inbox (reusable across verticals) + the SI trigger wrapper.
    app.state.notifications = NotificationService()
    app.state.sales_notifier = SalesNotificationService(notifications=app.state.notifications)
    app.state.sales_intel = OpportunityService(scan_interval_minutes=settings.idg_sales_scan_interval_minutes,
                                               notifier=app.state.sales_notifier)
    app.state.sales_intel_mutation = OpportunityMutationService(opportunities=app.state.sales_intel.opportunities,
                                                                 activity_logs=app.state.sales_intel.activity_logs,
                                                                 notifier=app.state.sales_notifier)
    app.state.salesforce_auth = SalesforceAuthService()
    app.state.salesforce_push = SalesforcePushService(auth=app.state.salesforce_auth,
                                                      notifier=app.state.sales_notifier)
    app.state.finance = FinanceService()
    app.state.teams = TeamService()
    app.state.leads = LeadService(get_email_sender())
    app.state.teams_notifier = TeamsNotifier()

    # Real client if the secret is configured, dev stub otherwise -- same pattern as
    # get_email_sender(). Gmail (as an agent tool, not transactional email) and Speech
    # (TTS/STT) have no real client yet, so those two stay stubbed.
    stripe_gateway = StripeClient() if settings.stripe_secret_key else StubStripeGateway()
    app.state.subscriptions = SubscriptionService(stripe_gateway)
    # Give the webhook the subscription service so checkout.session.completed can link the tenant
    # (from the session's client_reference_id) to its real Stripe customer id and activate.
    app.state.stripe_webhook = StripeWebhookHandler(subscriptions=app.state.subscriptions)
    app.state.whatsapp = WhatsAppAdapter(
        WhatsAppClient() if settings.whatsapp_access_token else StubWhatsAppGateway())
    app.state.excel = ExcelService(app.state.knowledge)
    app.state.sources = KnowledgeSources(app.state.knowledge)
    app.state.voice = VoicePipeline(StubSpeechGateway())
    app.state.signal_engine = SignalEngineClient() if settings.signal_engine_url else StubSignalEngine()
    app.state.customers = CustomerDirectory()
    app.state.ga4 = GA4Client() if settings.ga4_property_id and settings.ga4_access_token else StubGA4Gateway()
    app.state.payment_links = PaymentLinkService(gateway=stripe_gateway, email=get_email_sender())
    app.state.admin_org = AdminOrg()
    app.state.otp_store = OtpStore()
    app.state.channel_sessions = ChannelSessionStore()
    app.state.slack_oauth = SlackOAuth(InstallationStore())
    app.state.slack_links = WorkspaceLinkStore()
    app.state.file_generator = FileGenerator()
    app.state.task_queue = build_task_queue(task_registry)
    app.state.calendly = CalendlyClient() if settings.calendly_token else StubCalendlyGateway()
    app.state.gmail = StubGmailGateway()
    app.state.slack = SlackClient() if settings.slack_bot_token else StubSlackGateway()
    app.state.clickup = ClickUpClient() if settings.clickup_api_token else StubClickUpGateway()

    # Every request is tenant-scoped.
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api/v1", dependencies=[Depends(tenant_dependency)])
    for r in (identity_router, knowledge_router, agents_router, rfp_router, assignments_router, admin_router,
              chat_router, teams_router, leads_router, billing_router, channels_router, excel_router,
              voice_router, signal_router, public_chat_router, sources_router, twofa_router,
              onboarding_router, admin_org_router, batch_router, marketing_router, crm_router,
              sales_intelligence_router, finance_router, notifications_router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
