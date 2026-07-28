"""Shared FastAPI dependencies: authenticated tenant + RBAC + service singletons from app.state."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request

from app.core.config import get_settings
from app.core.tenancy import reset_tenant, set_tenant
from app.modules.identity.cookies import ACCESS_COOKIE
from app.modules.identity.rbac import Role, role_allows
from app.modules.identity.tokens import TokenError, decode_token


class WorkerUnavailable(Exception):
    pass


WorkerRecheck = Callable[[], Awaitable[None]]


async def require_available_worker(*, agents, tenant: str, agent_id: str):
    agent = await agents.get(tenant, agent_id)
    if agent is None or not agent.enabled:
        raise WorkerUnavailable
    return agent


async def current_claims(request: Request) -> dict:
    """Authenticate the request from the httpOnly access cookie (never a client header)."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        claims = decode_token(token, expected_type="access")
    except TokenError as e:
        raise HTTPException(status_code=401, detail="invalid or expired token") from e
    if get_settings().use_db_stores:
        subject, sid = claims.get("sub"), claims.get("sid")
        user = await get_user_store().get_by_id(subject) if subject and sid else None
        if user is None or user.current_sid != sid:
            raise HTTPException(status_code=401, detail="session revoked")
        claims = {
            **claims,
            "tenant": user.tenant,
            "role": user.role.value,
            "email": user.email,
        }
    return claims


async def authed_tenant(claims: dict = Depends(current_claims)):
    """Tenant is derived from the verified token claims (NOT a client header -> no BOLA)."""
    tenant = claims.get("tenant")
    if not tenant:
        raise HTTPException(status_code=403, detail="token has no tenant")
    token = set_tenant(tenant)
    try:
        yield tenant
    finally:
        reset_tenant(token)


def require_role(minimum: Role):
    """Dependency factory: require the authenticated user's role to meet `minimum`.

    This is the TENANT-scoped role (owner/admin/editor/viewer of the caller's own tenant) --
    "owner" ranks above "admin" here on purpose (an owner can do anything an admin can within
    their own tenant). It must never be used to gate cross-tenant platform-admin endpoints:
    every signed-up user is "owner" of their own tenant, so require_role(Role.admin) would let
    any customer into the admin panel. Use require_platform_admin/_super_admin for that instead.
    """
    def _dep(claims: dict = Depends(current_claims)) -> dict:
        if not role_allows(claims.get("role", "viewer"), minimum):
            raise HTTPException(status_code=403, detail="insufficient role")
        return claims
    return _dep


async def _platform_admin_role(request: Request, claims: dict = Depends(current_claims)):
    if not claims.get("mfa"):
        raise HTTPException(status_code=403, detail="platform admin MFA required")
    email = claims.get("email")
    role = await request.app.state.admin_org.role_of(email) if email else None
    if role is None:
        raise HTTPException(status_code=403, detail="platform admin access required")
    return role


def require_platform_admin():
    """Any registered platform admin (super_admin or read-only viewer) -- for read endpoints
    (customer directory, revenue, analytics). Completely separate from the tenant Role system."""
    def _dep(role=Depends(_platform_admin_role)):
        return role
    return _dep


def require_platform_super_admin():
    """Only a platform super_admin -- for mutating admin endpoints (delete/disable a customer,
    toggle Studio access, manage other admins)."""
    from app.modules.identity.admin_rbac import AdminRole

    def _dep(role=Depends(_platform_admin_role)):
        if role is not AdminRole.super_admin:
            raise HTTPException(status_code=403, detail="platform super_admin access required")
        return role
    return _dep


def get_knowledge(request: Request):
    return request.app.state.knowledge


def get_agents(request: Request):
    return request.app.state.agents


def get_rfp_packs(request: Request):
    return request.app.state.rfp_packs


def get_requirements(request: Request):
    return request.app.state.requirements


def get_pack_answers(request: Request):
    return request.app.state.pack_answers


def get_pack_tree(request: Request):
    return request.app.state.pack_tree


def get_user_store():
    """The identity UserStore (module-global, swapped for SqlUserStore at startup). Imported
    lazily to avoid a circular import between deps and the identity router."""
    from app.modules.identity.router import get_store

    return get_store()


def get_assignments(request: Request):
    return request.app.state.assignments


def get_crm(request: Request):
    return request.app.state.crm


def get_chat(request: Request):
    return request.app.state.chat


def get_teams(request: Request):
    return request.app.state.teams


def get_leads(request: Request):
    return request.app.state.leads


def get_subscriptions(request: Request):
    return request.app.state.subscriptions


def get_stripe_webhook(request: Request):
    return request.app.state.stripe_webhook


def get_whatsapp(request: Request):
    return request.app.state.whatsapp


def get_excel(request: Request):
    return request.app.state.excel


def get_sources(request: Request):
    return request.app.state.sources


def get_voice(request: Request):
    return request.app.state.voice


def get_payment_links(request: Request):
    return request.app.state.payment_links


def get_admin_org(request: Request):
    return request.app.state.admin_org


def get_otp_store(request: Request):
    return request.app.state.otp_store


def get_pending_invites(request: Request):
    return request.app.state.pending_invites


def get_channel_sessions(request: Request):
    return request.app.state.channel_sessions


def get_slack_oauth(request: Request):
    return request.app.state.slack_oauth


def get_slack_links(request: Request):
    return request.app.state.slack_links


def get_teams_notifier(request: Request):
    return request.app.state.teams_notifier


def get_file_generator(request: Request):
    return request.app.state.file_generator


def get_task_queue(request: Request):
    return request.app.state.task_queue


def get_calendly(request: Request):
    return request.app.state.calendly


def get_gmail(request: Request):
    return request.app.state.gmail


def get_slack(request: Request):
    return request.app.state.slack


def get_clickup(request: Request):
    return request.app.state.clickup


async def assemble_worker(*, sessionmaker, agents, knowledge, tenant: str, agent_id: str | None = None):
    """Assemble a Worker over the shared knowledge service + agentcore (agentic-first).

    Request-free core of build_tenant_worker: takes the raw collaborators (a DB sessionmaker for
    the feedback flywheel's verified store, the agents store for per-agent config, and the shared
    knowledge service) instead of a FastAPI Request, so the SAME Worker can be built off the
    request path -- e.g. by the background tender-generation job, which has no Request.

    Without `agent_id` this builds the generic tenant-wide config (unchanged default behaviour).
    With it, the specific Agent's own config (system_prompt / gate_threshold / retrieval_k, set
    via PUT /agents/{id}/config) is applied -- so two workers in the same tenant with different
    specialities (e.g. an RFP requirement-answering worker vs. a pre-sales content-writing worker)
    actually run different prompts/thresholds instead of silently sharing one identical worker.
    The feedback flywheel (verified answers) persists to Postgres when USE_DB_STORES is on, so
    human-approved answers survive a redeploy instead of living only in process memory."""
    from app.modules.agentcore.generator import Generator
    from app.modules.agentcore.runtime import AgentCore
    from app.modules.workers.config import WorkerConfig
    from app.modules.workers.worker import Worker

    verified = None
    if get_settings().use_db_stores and sessionmaker is not None:
        from app.db.stores import SqlVerifiedStore

        verified = SqlVerifiedStore(sessionmaker)

    cfg = {}
    if agent_id:
        agent = await agents.get(tenant, agent_id)
        if agent is not None:
            cfg = agent.config
    kwargs = {"name": f"w-{tenant}-{agent_id}" if agent_id else f"w-{tenant}", "tenant": tenant}
    if "gate_threshold" in cfg:
        kwargs["gate_threshold"] = cfg["gate_threshold"]
    if "retrieval_k" in cfg:
        kwargs["retrieval_k"] = cfg["retrieval_k"]
    if cfg.get("system_prompt"):
        kwargs["system_prompt"] = cfg["system_prompt"]
    worker_config = WorkerConfig(**kwargs)
    return Worker(config=worker_config, knowledge=knowledge,
                  agent=AgentCore(generator=Generator(system_prompt=worker_config.system_prompt),
                                  threshold=worker_config.gate_threshold, verified=verified))


async def resolve_available_worker(*, sessionmaker, agents, knowledge, tenant: str,
                                   agent_id: str, assembler=None) -> tuple[object, WorkerRecheck]:
    async def recheck() -> None:
        await require_available_worker(agents=agents, tenant=tenant, agent_id=agent_id)

    await recheck()
    worker = await (assembler or assemble_worker)(
        sessionmaker=sessionmaker, agents=agents, knowledge=knowledge,
        tenant=tenant, agent_id=agent_id)
    await recheck()
    return worker, recheck


async def resolve_tenant_worker(request: Request, tenant: str,
                                agent_id: str) -> tuple[object, WorkerRecheck]:
    return await resolve_available_worker(
        sessionmaker=getattr(request.app.state, "sessionmaker", None),
        agents=request.app.state.agents, knowledge=request.app.state.knowledge,
        tenant=tenant, agent_id=agent_id)


async def build_tenant_worker(request: Request, tenant: str, agent_id: str | None = None):
    """Assemble a tenant/agent Worker from app.state (thin Request-bound wrapper over
    assemble_worker -- see there for the config/flywheel semantics)."""
    return await assemble_worker(
        sessionmaker=getattr(request.app.state, "sessionmaker", None),
        agents=request.app.state.agents, knowledge=request.app.state.knowledge,
        tenant=tenant, agent_id=agent_id)
