"""Read-only source connectors for the Intelligence Worker.

Each connector implements the `Connector` Protocol from `app.modules.intelligence.catalog`.
Nothing here writes to the third party; `verify()` performs read-only checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
