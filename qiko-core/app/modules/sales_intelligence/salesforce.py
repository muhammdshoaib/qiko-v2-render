"""Real IDG Sales Salesforce integration: authorization_code + PKCE OAuth2 with refresh, and
Opportunity push. Faithful port of:
 - app/Services/IdgSales/Salesforce/SalesforceAuthService.php
 - app/Services/IdgSales/Salesforce/SalesforceOpportunityPushService.php

DISCREPANCY vs. app.integrations.clients.SalesforceClient / app.modules.crm's Salesforce
integration (built this session): that generic per-worker connector uses the
`client_credentials` grant (server-to-server, no user redirect) -- explicitly documented there as
"the simplest real integration shape", not the branch's flow. The REAL, working IDG Sales
Salesforce connection is a full `authorization_code` + PKCE (S256) browser-redirect OAuth2 flow
with `refresh_token`, matching a normal user-consented Salesforce Connected App -- this module
implements *that* flow, faithfully, and does not touch app.integrations.clients.SalesforceClient.

Access/refresh tokens are encrypted at rest via app.core.crypto (Fernet), same as every other
integration secret in qiko-core (Teams webhook URL, channel session tokens) -- mirroring the
Laravel model's `'access_token' => 'encrypted'` cast.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.modules.sales_intelligence.models import (
    ActivityLog,
    ActivityLogStore,
    InMemoryActivityLogStore,
    InMemorySalesforceConnectionStore,
    OpportunityStore,
    SalesforceConnection,
    SalesforceConnectionStore,
)
from app.modules.sales_intelligence.notifications import SalesNotificationService


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SalesforceError(RuntimeError):
    pass


class SalesforceNotConfiguredError(SalesforceError):
    pass


@dataclass
class _OAuthState:
    tenant: str
    agent_id: str
    actor_user_id: str | None
    code_verifier: str


@dataclass
class SalesforceAuthService:
    connections: SalesforceConnectionStore = field(default_factory=InMemorySalesforceConnectionStore)
    activity_logs: ActivityLogStore = field(default_factory=InMemoryActivityLogStore)
    client: httpx.Client | None = None
    _state_cache: dict[str, _OAuthState] = field(default_factory=dict)

    def _http(self) -> httpx.Client:
        return self.client or httpx.Client(timeout=30.0)

    def redirect_uri(self) -> str:
        s = get_settings()
        uri = (s.salesforce_redirect_uri or f"{s.public_base_url.rstrip('/')}/api/v1/sales-intelligence/salesforce/oauth/callback")
        return uri.rstrip("/")

    def assert_configured(self) -> None:
        s = get_settings()
        if not (s.salesforce_client_id and s.salesforce_client_secret and self.redirect_uri()):
            raise SalesforceNotConfiguredError(
                "Salesforce OAuth is not configured. Set SALESFORCE_CLIENT_ID, "
                "SALESFORCE_CLIENT_SECRET, and SALESFORCE_REDIRECT_URI.")

    async def get_or_create_connection(self, tenant: str, agent_id: str) -> SalesforceConnection:
        return await self.connections.get_or_create(tenant, agent_id)

    def _generate_code_verifier(self) -> str:
        return base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()

    def _generate_code_challenge(self, code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def build_authorize_url(self, tenant: str, agent_id: str, actor_user_id: str | None = None) -> dict:
        self.assert_configured()
        s = get_settings()
        state = secrets.token_urlsafe(30)
        code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(code_verifier)
        self._state_cache[state] = _OAuthState(tenant=tenant, agent_id=agent_id, actor_user_id=actor_user_id,
                                                code_verifier=code_verifier)

        query = urlencode({
            "response_type": "code", "client_id": s.salesforce_client_id, "redirect_uri": self.redirect_uri(),
            "scope": s.salesforce_scopes, "state": state, "prompt": "login consent",
            "code_challenge": code_challenge, "code_challenge_method": "S256",
        })
        login_base = s.salesforce_login_base_url.rstrip("/")
        return {"authorizeUrl": f"{login_base}/services/oauth2/authorize?{query}", "state": state}

    async def handle_callback(self, code: str, state: str) -> dict:
        self.assert_configured()
        pending = self._state_cache.pop(state, None)
        if pending is None:
            raise SalesforceError("Invalid or expired Salesforce OAuth state.")

        token_response = self._exchange_authorization_code(code, pending.code_verifier)
        connection = await self.connections.get_or_create(pending.tenant, pending.agent_id)
        connection.status = "connected"
        connection.connected_by_user_id = pending.actor_user_id
        connection.instance_url = token_response.get("instance_url")
        connection.access_token = encrypt(token_response["access_token"])
        if token_response.get("refresh_token"):
            connection.refresh_token = encrypt(token_response["refresh_token"])
        connection.token_type = token_response.get("token_type", "Bearer")
        connection.token_expires_at = _now() + timedelta(hours=2)
        connection.salesforce_user_id = self._parse_id_from_url(token_response.get("id"), "user")
        connection.salesforce_org_id = self._parse_id_from_url(token_response.get("id"), "org")
        connection.last_error = None
        connection.connected_at = _now()
        connection = await self.connections.update(connection)

        await self.activity_logs.add(ActivityLog(
            id=secrets.token_hex(6), tenant=pending.tenant, agent_id=pending.agent_id,
            actor_user_id=pending.actor_user_id, action="salesforce_connected",
            detail="Salesforce OAuth connected for this agent.", tone="success",
            metadata={"instance_url": connection.instance_url, "salesforce_org_id": connection.salesforce_org_id},
        ))
        return {"connection": connection, "agent_id": pending.agent_id}

    async def disconnect(self, tenant: str, agent_id: str, actor_user_id: str | None = None) -> SalesforceConnection:
        connection = await self.connections.get_or_create(tenant, agent_id)
        connection.status = "disconnected"
        connection.access_token = None
        connection.refresh_token = None
        connection.instance_url = None
        connection.token_type = None
        connection.token_expires_at = None
        connection.salesforce_user_id = None
        connection.salesforce_org_id = None
        connection.last_error = None
        connection.connected_at = None
        connection.connected_by_user_id = None
        connection = await self.connections.update(connection)
        await self.activity_logs.add(ActivityLog(
            id=secrets.token_hex(6), tenant=tenant, agent_id=agent_id, actor_user_id=actor_user_id,
            action="salesforce_disconnected", detail="Salesforce connection removed for this agent.", tone="info",
        ))
        return connection

    def get_valid_access_token(self, connection: SalesforceConnection) -> str:
        if not connection.is_connected():
            raise SalesforceError("Salesforce is not connected for this agent.")
        if (connection.token_expires_at and connection.token_expires_at > _now() + timedelta(minutes=2)
                and connection.access_token):
            return decrypt(connection.access_token)
        if not connection.refresh_token:
            connection.status = "expired"
            connection.last_error = "Salesforce access token expired and no refresh token is available."
            raise SalesforceError("Salesforce session expired. Reconnect Salesforce.")
        return self.refresh_access_token(connection)

    def refresh_access_token(self, connection: SalesforceConnection) -> str:
        self.assert_configured()
        s = get_settings()
        login_base = s.salesforce_login_base_url.rstrip("/")
        response = self._http().post(f"{login_base}/services/oauth2/token", data={
            "grant_type": "refresh_token", "client_id": s.salesforce_client_id,
            "client_secret": s.salesforce_client_secret, "refresh_token": decrypt(connection.refresh_token),
        })
        if response.status_code >= 300:
            message = self._extract_error_message(response, "Salesforce token refresh failed.")
            connection.status = "expired"
            connection.last_error = message
            raise SalesforceError(message)

        data = response.json() if response.content else {}
        connection.status = "connected"
        if data.get("access_token"):
            connection.access_token = encrypt(data["access_token"])
        if data.get("instance_url"):
            connection.instance_url = data["instance_url"]
        connection.token_type = data.get("token_type", connection.token_type)
        connection.token_expires_at = _now() + timedelta(hours=2)
        connection.last_error = None
        return decrypt(connection.access_token)

    def _exchange_authorization_code(self, code: str, code_verifier: str | None) -> dict:
        s = get_settings()
        login_base = s.salesforce_login_base_url.rstrip("/")
        payload = {
            "grant_type": "authorization_code", "code": code, "client_id": s.salesforce_client_id,
            "client_secret": s.salesforce_client_secret, "redirect_uri": self.redirect_uri(),
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier

        response = self._http().post(f"{login_base}/services/oauth2/token", data=payload)
        if response.status_code >= 300:
            raise SalesforceError(self._extract_error_message(response, "Salesforce authorization code exchange failed."))

        data = response.json() if response.content else {}
        if not data.get("access_token") or not data.get("instance_url"):
            raise SalesforceError("Salesforce token response did not include access_token/instance_url.")
        return data

    def _parse_id_from_url(self, identity_url: str | None, part: str) -> str | None:
        if not identity_url:
            return None
        segments = identity_url.strip("/").split("/")
        if len(segments) < 2:
            return None
        return segments[-2] if part == "org" else segments[-1]

    def _extract_error_message(self, response: httpx.Response, fallback: str) -> str:
        try:
            data = response.json()
        except Exception:
            return fallback
        if not isinstance(data, dict):
            return fallback
        message = data.get("error_description") or data.get("error") or data.get("message")
        return message if isinstance(message, str) and message else fallback


@dataclass
class SalesforcePushService:
    auth: SalesforceAuthService
    activity_logs: ActivityLogStore = field(default_factory=InMemoryActivityLogStore)
    client: httpx.Client | None = None
    notifier: SalesNotificationService | None = None
    # Persist the opportunity's stage / salesforce_* columns after a push. Without this the mutated
    # object is only saved by luck under the in-memory store (get() returns the same reference); the
    # Postgres store returns a fresh object each get(), so push results would be silently lost.
    opportunities: OpportunityStore | None = None

    def _http(self) -> httpx.Client:
        return self.client or httpx.Client(timeout=45.0)

    async def _persist(self, opportunity, connection: SalesforceConnection) -> None:
        if self.opportunities is not None:
            await self.opportunities.update(opportunity)
        await self.auth.connections.update(connection)

    async def push(self, opportunity, actor_user_id: str | None = None):
        import secrets as _secrets

        if opportunity.stage not in ("validated", "push_failed", "ready_salesforce"):
            raise SalesforceError(f"Only validated opportunities can be pushed to Salesforce. Current stage: {opportunity.stage}")

        connection = await self.auth.get_or_create_connection(opportunity.tenant, opportunity.agent_id)
        if not connection.is_connected():
            raise SalesforceError("Salesforce is not connected for this agent. Connect Salesforce first.")

        opportunity.stage = "push_pending"
        opportunity.salesforce_push_status = "pending"
        opportunity.salesforce_push_error = None

        await self.activity_logs.add(ActivityLog(
            id=_secrets.token_hex(6), tenant=opportunity.tenant, agent_id=opportunity.agent_id,
            opportunity_id=opportunity.id, actor_user_id=actor_user_id, action="salesforce_push_started",
            detail=f"Salesforce push started: {opportunity.title}", tone="info",
            metadata={"opportunity_id": opportunity.id, "external_id": opportunity.external_id},
        ))

        try:
            access_token = self.auth.get_valid_access_token(connection)
            payload = self._map_opportunity_payload(opportunity)
            try:
                sf_id = self._create_opportunity(connection, access_token, payload)
            except SalesforceError as e:
                if "unauthorized" not in str(e).lower() and "401" not in str(e):
                    raise
                access_token = self.auth.refresh_access_token(connection)
                sf_id = self._create_opportunity(connection, access_token, payload)

            opportunity.stage = "pushed"
            opportunity.salesforce_push_status = "success"
            opportunity.salesforce_opportunity_id = sf_id
            opportunity.salesforce_pushed_at = _now()
            opportunity.salesforce_push_error = None

            await self.activity_logs.add(ActivityLog(
                id=_secrets.token_hex(6), tenant=opportunity.tenant, agent_id=opportunity.agent_id,
                opportunity_id=opportunity.id, actor_user_id=actor_user_id, action="salesforce_push_succeeded",
                detail=f"Pushed to Salesforce Opportunity {sf_id}", tone="success",
                metadata={"salesforceOpportunityId": sf_id, "salesforce_id": sf_id, "instance_url": connection.instance_url},
            ))
            await self._persist(opportunity, connection)
            # Notification trigger: Salesforce sync successful.
            if self.notifier is not None:
                await self.notifier.notify_salesforce_sync_success(opportunity, sf_id)
            return opportunity
        except Exception as e:
            message = str(e)
            opportunity.stage = "push_failed"
            opportunity.salesforce_push_status = "failed"
            opportunity.salesforce_push_error = message
            connection.last_error = message

            await self.activity_logs.add(ActivityLog(
                id=_secrets.token_hex(6), tenant=opportunity.tenant, agent_id=opportunity.agent_id,
                opportunity_id=opportunity.id, actor_user_id=actor_user_id, action="salesforce_push_failed",
                detail=message, tone="danger", metadata={"opportunity_id": opportunity.id},
            ))
            await self._persist(opportunity, connection)
            # Notification trigger: Salesforce sync failed.
            if self.notifier is not None:
                await self.notifier.notify_salesforce_sync_failed(opportunity, message)
            raise

    def _map_opportunity_payload(self, opportunity) -> dict:
        s = get_settings()
        close_date = (opportunity.deadline_at.astimezone(timezone.utc).date().isoformat()
                      if opportunity.deadline_at else (_now() + timedelta(days=30)).date().isoformat())

        description_parts = [p for p in [
            opportunity.qualification_summary,
            f"Source URL: {opportunity.source_url}" if opportunity.source_url else None,
            f"External ID ({opportunity.source_key.upper()}): {opportunity.external_id}" if opportunity.external_id else None,
            f"Buyer: {opportunity.buyer}" if opportunity.buyer else None,
            f"Country: {opportunity.country}" if opportunity.country else None,
            f"Category: {opportunity.category}" if opportunity.category else None,
            f"Review notes: {opportunity.human_review_notes}" if opportunity.human_review_notes else None,
        ] if p]

        payload = {
            "Name": (opportunity.title or "")[:120],
            "StageName": s.salesforce_default_stage_name,
            "CloseDate": close_date,
            "Description": "\n".join(description_parts)[:32000],
        }
        if opportunity.estimated_value is not None:
            payload["Amount"] = float(opportunity.estimated_value)
        if s.salesforce_external_id_field and opportunity.external_id:
            payload[s.salesforce_external_id_field] = f"{opportunity.source_key.upper()}:{opportunity.external_id}"
        return payload

    def _create_opportunity(self, connection: SalesforceConnection, access_token: str, payload: dict) -> str:
        s = get_settings()
        api_version = s.salesforce_api_version.strip("/")
        url = f"{connection.instance_url.rstrip('/')}/services/data/{api_version}/sobjects/Opportunity"
        response = self._http().post(url, json=payload, headers={
            "Authorization": f"Bearer {access_token}", "Accept": "application/json"})

        if response.status_code == 401:
            raise SalesforceError("Salesforce API unauthorized (401).")
        if response.status_code >= 300:
            raise SalesforceError(self._format_error(response))

        data = response.json() if response.content else {}
        sf_id = data.get("id")
        if not isinstance(sf_id, str) or not sf_id:
            raise SalesforceError("Salesforce create Opportunity response did not include an id.")
        return sf_id

    def _format_error(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except Exception:
            data = None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            message = data[0].get("message")
            error_code = data[0].get("errorCode")
            if message:
                return f"{error_code}: {message}" if error_code else message
        if isinstance(data, dict) and isinstance(data.get("message"), str):
            return data["message"]
        return f"Salesforce Opportunity create failed with status {response.status_code}."
