"""Microsoft Teams Integration: notifications + collaboration via a per-tenant Incoming Webhook.

Deliberately the simplest real integration shape (a webhook URL the tenant generates themselves
in their own Teams channel -- Teams > Channel > Connectors > Incoming Webhook), not a full
Azure AD app registration + Graph API OAuth flow. That would need tenant-admin consent and an
app registration per customer; a webhook URL is something any Teams channel owner can create in
under a minute and paste in, which is what "Notifications and collaboration via Microsoft Teams"
actually needs: push events (tender won/lost, new assignment, ...) into a channel, not two-way
Graph API access.

The webhook URL is encrypted at rest (app.core.crypto) -- like a bot token, it lets anyone with it
post into the customer's Teams channel, so it gets the same treatment as the Vapi API key.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.core.crypto import decrypt, encrypt


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TeamsIntegration:
    tenant: str
    enc_webhook_url: str
    connected_at: datetime = field(default_factory=_now)


class TeamsGateway(Protocol):
    def send(self, webhook_url: str, text: str) -> None: ...


class TeamsIntegrationStore(Protocol):
    async def get(self, tenant: str) -> TeamsIntegration | None: ...
    async def set(self, tenant: str, webhook_url: str) -> TeamsIntegration: ...
    async def delete(self, tenant: str) -> None: ...


@dataclass
class InMemoryTeamsIntegrationStore:
    _by_tenant: dict[str, TeamsIntegration] = field(default_factory=dict)

    async def get(self, tenant: str) -> TeamsIntegration | None:
        return self._by_tenant.get(tenant)

    async def set(self, tenant: str, webhook_url: str) -> TeamsIntegration:
        integration = TeamsIntegration(tenant=tenant, enc_webhook_url=encrypt(webhook_url))
        self._by_tenant[tenant] = integration
        return integration

    async def delete(self, tenant: str) -> None:
        self._by_tenant.pop(tenant, None)


class TeamsWebhookError(Exception):
    pass


@dataclass
class TeamsNotifier:
    """Tenant-facing service: connect/disconnect a webhook, and fire notifications that must
    never break the caller's actual workflow if the webhook is missing/broken (see `notify`)."""
    store: TeamsIntegrationStore = None  # type: ignore[assignment]
    gateway: TeamsGateway = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryTeamsIntegrationStore()
        if self.gateway is None:
            from app.integrations.clients import TeamsWebhookClient

            self.gateway = TeamsWebhookClient()

    async def status(self, tenant: str) -> dict:
        integration = await self.store.get(tenant)
        return {"connected": integration is not None,
               "connected_at": integration.connected_at.isoformat() if integration else None}

    async def connect(self, tenant: str, webhook_url: str) -> None:
        if not webhook_url.startswith("https://"):
            raise TeamsWebhookError("webhook URL must be an https:// URL")
        await self.store.set(tenant, webhook_url)

    async def disconnect(self, tenant: str) -> None:
        await self.store.delete(tenant)

    async def send_test(self, tenant: str) -> None:
        integration = await self.store.get(tenant)
        if integration is None:
            raise TeamsWebhookError("no Teams webhook connected for this tenant")
        # gateway.send is a blocking network call -- run off the event loop thread so it can't
        # freeze every other request this process is handling for its entire duration.
        await asyncio.to_thread(self.gateway.send, decrypt(integration.enc_webhook_url),
                                "\u2705 Qiko is connected to this Teams channel.")

    async def notify(self, tenant: str, text: str) -> bool:
        """Best-effort: swallow any failure (missing webhook, dead URL, Teams outage) so a
        notification never takes down the real action (recording an outcome, an assignment...)
        that triggered it. Returns whether it actually sent."""
        integration = await self.store.get(tenant)
        if integration is None:
            return False
        try:
            await asyncio.to_thread(self.gateway.send, decrypt(integration.enc_webhook_url), text)
            return True
        except Exception:
            return False
