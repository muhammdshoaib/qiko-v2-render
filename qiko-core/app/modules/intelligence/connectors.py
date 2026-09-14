"""Read-only source connectors for the Intelligence Worker.

Each connector implements the `Connector` Protocol from `app.modules.intelligence.catalog`.
Nothing here writes to the third party; `verify()` performs read-only checks.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.modules.intelligence.github_client import GitHubClient, GitHubClientError
from app.modules.intelligence.models import Signal
from app.modules.intelligence.qiko_track_client import QikoTrackClient, QikoTrackClientError
from app.modules.intelligence.qiko_track_history import PollAndDiff
from app.modules.sales_intelligence.ssrf import SsrfError


@dataclass
class GitHubConnector:
    """Read-only GitHub connector: PAT or GitHub App installation token."""

    key: str = "github"
    transport: Any | None = field(default=None, repr=False)
    resolver: Any | None = field(default=None, repr=False)

    def _base_url(self, config: dict) -> str:
        return config.get("base_url") or get_settings().github_api_base

    async def fetch_since(self, *, config: dict, credential: str,
                          since: Any, tenant: str, agent_id: str,
                          signal_store: Any | None = None) -> list[Signal]:
        """Poll connector and return normalised signals."""
        client = GitHubClient(
            credential, base_url=self._base_url(config),
            transport=self.transport, resolver=self.resolver)
        return await client.fetch_signals(
            config=config, since=since, tenant=tenant, agent_id=agent_id)

    async def verify(self, *, config: dict, credential: str) -> dict:
        if not credential:
            return {"ok": False, "error": "GitHub token or installation id is required"}
        try:
            client = GitHubClient(
                credential, base_url=self._base_url(config),
                transport=self.transport, resolver=self.resolver)
        except SsrfError as exc:
            return {"ok": False, "error": f"unsafe base URL: {exc}"}
        except GitHubClientError as exc:
            return {"ok": False, "error": str(exc)}
        return await client.verify(config.get("repo_allowlist") or [])


@dataclass
class QikoTrackConnector:
    """Read-only Qiko Track connector: verify token and emit normalised signals."""

    key: str = "qiko_track"
    transport: Any | None = field(default=None, repr=False)
    resolver: Any | None = field(default=None, repr=False)
    history_strategy: Any = field(default_factory=PollAndDiff, repr=False)

    def _base_url(self, config: dict) -> str:
        return config.get("base_url") or get_settings().qiko_track_api_base

    def _project_keys(self, config: dict) -> list[str]:
        keys = config.get("project_keys") or []
        if isinstance(keys, str):
            keys = [keys]
        return [k.strip() for k in keys if k and k.strip()]

    async def fetch_since(self, *, config: dict, credential: str,
                          since: Any, tenant: str, agent_id: str,
                          signal_store: Any | None = None) -> list[Signal]:
        """Poll connector; emits one Signal per observed ticket change."""
        if self.history_strategy is None:
            return []
        return await self.history_strategy.fetch(
            base_url=self._base_url(config),
            token=credential,
            project_keys=self._project_keys(config),
            tenant=tenant,
            agent_id=agent_id,
            signal_store=signal_store,
            since=since,
            transport=self.transport,
            resolver=self.resolver,
        )

    async def verify(self, *, config: dict, credential: str) -> dict:
        if not credential:
            return {"ok": False, "error": "Qiko Track token is required"}

        project_keys = self._project_keys(config)
        if not project_keys:
            return {"ok": False, "error": "at least one project key is required"}

        base_url = self._base_url(config)
        try:
            client = QikoTrackClient(
                base_url, credential, transport=self.transport, resolver=self.resolver)
            context = await client.get_context()
        except SsrfError as exc:
            return {"ok": False, "error": f"unsafe base URL: {exc}"}
        except QikoTrackClientError as exc:
            return {"ok": False, "error": str(exc)}

        actor = context.get("actor") or {}
        projects = context.get("projects") or []
        visible = [{"key": p.get("key"), "name": p.get("name")} for p in projects]
        return {
            "ok": True,
            "actor": {
                "name": actor.get("name"),
                "email": actor.get("email"),
                "role": actor.get("role"),
                "scopes": actor.get("scopes") or [],
            },
            "scopes": actor.get("scopes") or [],
            "projects": visible,
        }


@dataclass
class GA4Connector:
    """Read-only GA4 (Google Analytics Data API) connector.

    Unlike GitHub/Qiko Track, GA4 credentials are GLOBAL (one property for the whole product,
    the same one the admin dashboard already reads via GA4Client) rather than per-worker.
    A worker "connects" GA4 by setting a flag; there is nothing to paste. `credential` is
    accepted for protocol symmetry with every other Connector but is expected to be empty here -
    GA4Client falls back to Settings.ga4_access_token when given one, exactly like the admin
    dashboard's own construction (see app.integrations.clients.GA4Client.__init__).
    """

    key: str = "ga4"
    http_client: Any | None = field(default=None, repr=False)

    def _client(self, config: dict, credential: str):
        from app.integrations.clients import GA4Client

        # No per-agent property override: GA4 always resolves the property from
        # Settings.ga4_property_id, exactly like the access token. Allowing a per-agent
        # property id here would let any tenant read another tenant's GA4 property through
        # this shared, global credential (see GA4Client.__init__'s own fallback).
        return GA4Client(
            property_id=None,
            access_token=credential or None,
            client=self.http_client)

    async def fetch_since(self, *, config: dict, credential: str,
                          since: Any, tenant: str, agent_id: str,
                          signal_store: Any | None = None) -> list[Signal]:
        client = self._client(config, credential)
        start = since.strftime("%Y-%m-%d")
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = await asyncio.to_thread(
            client.run_report, start, end, ["sessions", "activeUsers"], ["date"])

        signals: list[Signal] = []
        for row in rows:
            raw_date = row.get("date", "")
            try:
                occurred_at = datetime.strptime(raw_date, "%Y%m%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            sessions = row.get("sessions", "0")
            active_users = row.get("activeUsers", "0")
            signals.append(Signal(
                tenant=tenant, agent_id=agent_id, source="ga4", kind="traffic_snapshot",
                external_id=f"ga4-{raw_date}", container="ga4", actor="",
                title=f"Traffic on {occurred_at.date().isoformat()}: "
                      f"{sessions} sessions, {active_users} active users",
                body=f"sessions={sessions} active_users={active_users}",
                occurred_at=occurred_at,
                meta={"sessions": sessions, "active_users": active_users},
            ))
        return signals

    async def verify(self, *, config: dict, credential: str) -> dict:
        client = self._client(config, credential)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            await asyncio.to_thread(
                client.run_report, yesterday, today, ["sessions"], ["date"])
        except Exception as exc:  # noqa: BLE001 - surfaced to the Test button, not raised
            return {"ok": False, "error": str(exc)}
        return {"ok": True}
