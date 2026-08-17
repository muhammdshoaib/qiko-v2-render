"""Slack OAuth install + multi-workspace installation store + workspace-user -> Qiko worker linking.

Ports the standalone slack-app (postgresInstallationStore.ts / userSessions.ts / createApp.ts) into
qiko-core so slack-app can be decommissioned. The OAuth token exchange takes an injectable
httpx.Client for unit-testing without network.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field, replace
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt


@dataclass
class SlackInstallation:
    team_id: str
    bot_token: str
    bot_user_id: str
    enterprise_id: str | None = None
    installed_by: str | None = None
    tenant: str | None = None
    worker_id: str | None = None


def _install_key(tenant: str | None, team_id: str, enterprise_id: str | None) -> str:
    return f"{tenant or '-'}:{enterprise_id or '-'}:{team_id}"


@dataclass
class InstallationStore:
    """Multi-workspace installation store (in-memory; swap for a SqlSlackInstallationStore in prod)."""
    _installs: dict[str, SlackInstallation] = field(default_factory=dict)

    def save(self, inst: SlackInstallation) -> None:
        # Bot token is encrypted at rest (Fernet); never stored in plaintext.
        self._installs[_install_key(inst.tenant, inst.team_id, inst.enterprise_id)] = replace(
            inst, bot_token=encrypt(inst.bot_token))

    def fetch(self, team_id: str, enterprise_id: str | None = None,
              tenant: str | None = None) -> SlackInstallation | None:
        inst = self._installs.get(_install_key(tenant, team_id, enterprise_id))
        return replace(inst, bot_token=decrypt(inst.bot_token)) if inst else None

    def delete(self, team_id: str, enterprise_id: str | None = None,
               tenant: str | None = None) -> None:
        self._installs.pop(_install_key(tenant, team_id, enterprise_id), None)

    def fetch_by_workspace(self, team_id: str,
                           enterprise_id: str | None = None) -> SlackInstallation | None:
        """Resolve an INSTALLED Slack workspace to its Qiko tenant/worker.

        The Events API payload does not carry the Qiko tenant, so it has to be reverse-looked-up
        from the workspace. Two properties make that safe, and both were absent from the first
        version of this method:

        AMBIGUITY IS REFUSED. The key is (team_id, enterprise_id), and if more than one Qiko
        tenant has installed the app into the same workspace, this returns None rather than the
        first match the dict happens to yield. Returning a match would decide, by iteration
        order, which tenant's database a third party's messages are written into -- a
        cross-tenant write with no way to notice it happened.

        AN UNOWNED INSTALLATION IS NOT A TENANT. `exchange_code(save=True)` can persist an
        installation with tenant=None (it is used by the standalone token exchange), and treating
        that as a tenant meant writing rows under an empty tenant_id, where two unrelated
        workspaces sharing a channel id would be merged into one digest. Those installations are
        skipped here instead.

        Multi-tenant deployments should back this with a SQL index on (team_id, enterprise_id).
        """
        matches = [inst for inst in self._installs.values()
                   if inst and inst.team_id == team_id
                   and (inst.enterprise_id or None) == (enterprise_id or None)
                   and inst.tenant]
        if len(matches) != 1:
            return None
        return replace(matches[0], bot_token=decrypt(matches[0].bot_token))


@dataclass
class WorkspaceLinkStore:
    """Links a tenant's Slack workspace user to a Qiko worker/agent."""
    _links: dict[tuple[str, str, str], str] = field(default_factory=dict)

    def link(self, tenant: str, team_id: str, slack_user_id: str, worker_id: str) -> None:
        self._links[(tenant, team_id, slack_user_id)] = worker_id

    def resolve(self, tenant: str, team_id: str, slack_user_id: str) -> str | None:
        return self._links.get((tenant, team_id, slack_user_id))


class SlackOAuthError(Exception):
    pass


@dataclass
class _SlackState:
    tenant: str
    worker_id: str
    actor_user_id: str | None
    expires_at: float


@dataclass
class SlackOAuth:
    store: InstallationStore
    client: httpx.Client | None = None
    _states: dict[str, _SlackState] = field(default_factory=dict)

    def install_url(self, state: str) -> str:
        s = get_settings()
        params = {"client_id": s.slack_client_id, "scope": s.slack_scopes,
                  "redirect_uri": s.slack_redirect_uri, "state": state}
        return "https://slack.com/oauth/v2/authorize?" + urlencode(params)

    def create_install(
        self, tenant: str, worker_id: str, actor_user_id: str | None,
    ) -> dict:
        state = secrets.token_urlsafe(32)
        self._states[state] = _SlackState(
            tenant=tenant, worker_id=worker_id, actor_user_id=actor_user_id,
            expires_at=time.monotonic() + 600,
        )
        return {"url": self.install_url(state), "state": state}

    async def complete_install(self, code: str, state: str, *, recheck_worker) -> SlackInstallation:
        pending = self._states.pop(state, None)
        if pending is None or pending.expires_at < time.monotonic():
            raise SlackOAuthError("invalid or expired OAuth state")
        await recheck_worker(pending.tenant, pending.worker_id)
        try:
            installation = await asyncio.to_thread(self.exchange_code, code, False)
        finally:
            await recheck_worker(pending.tenant, pending.worker_id)
        installation.tenant = pending.tenant
        installation.worker_id = pending.worker_id
        installation.installed_by = pending.actor_user_id or installation.installed_by
        # The production store is synchronous (app/db/sync_stores.py), so the write goes to a
        # thread rather than blocking this coroutine's event loop.
        await asyncio.to_thread(self.store.save, installation)
        return installation

    def exchange_code(self, code: str, save: bool = True) -> SlackInstallation:
        s = get_settings()
        c = self.client or httpx.Client(timeout=15.0)
        r = c.post("https://slack.com/api/oauth.v2.access",
                   data={"client_id": s.slack_client_id, "client_secret": s.slack_client_secret,
                         "code": code, "redirect_uri": s.slack_redirect_uri})
        r.raise_for_status()
        body = r.json()
        if not body.get("ok"):
            raise SlackOAuthError(body.get("error", "oauth_failed"))
        inst = SlackInstallation(
            team_id=body["team"]["id"],
            enterprise_id=(body.get("enterprise") or {}).get("id"),
            bot_token=body["access_token"],
            bot_user_id=body["bot_user_id"],
            installed_by=(body.get("authed_user") or {}).get("id"),
        )
        if save:
            self.store.save(inst)
        return inst
