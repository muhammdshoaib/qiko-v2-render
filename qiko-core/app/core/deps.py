"""Shared FastAPI dependencies: authenticated tenant + RBAC + service singletons from app.state."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.core.tenancy import reset_tenant, set_tenant
from app.modules.identity.cookies import ACCESS_COOKIE
from app.modules.identity.rbac import Role, role_allows
from app.modules.identity.tokens import TokenError, decode_token


def current_claims(request: Request) -> dict:
    """Authenticate the request from the httpOnly access cookie (never a client header)."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        return decode_token(token, expected_type="access")
    except TokenError as e:
        raise HTTPException(status_code=401, detail="invalid or expired token") from e


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
    """Dependency factory: require the authenticated user's role to meet `minimum`."""
    def _dep(claims: dict = Depends(current_claims)) -> dict:
        if not role_allows(claims.get("role", "viewer"), minimum):
            raise HTTPException(status_code=403, detail="insufficient role")
        return claims
    return _dep


def get_knowledge(request: Request):
    return request.app.state.knowledge


def get_agents(request: Request):
    return request.app.state.agents


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


def get_channel_sessions(request: Request):
    return request.app.state.channel_sessions


def get_slack_oauth(request: Request):
    return request.app.state.slack_oauth


def get_slack_links(request: Request):
    return request.app.state.slack_links


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


def build_tenant_worker(request: Request, tenant: str):
    """Assemble a per-tenant Worker over the shared knowledge service + agentcore (agentic-first)."""
    from app.modules.agentcore.generator import Generator
    from app.modules.agentcore.runtime import AgentCore
    from app.modules.workers.config import WorkerConfig
    from app.modules.workers.worker import Worker

    return Worker(config=WorkerConfig(name=f"w-{tenant}", tenant=tenant),
                  knowledge=request.app.state.knowledge, agent=AgentCore(generator=Generator()))
