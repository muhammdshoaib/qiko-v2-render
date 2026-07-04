"""Slack OAuth install + multi-workspace installation store + workspace-user -> Qiko worker linking.

Ports the standalone slack-app (postgresInstallationStore.ts / userSessions.ts / createApp.ts) into
qiko-core so slack-app can be decommissioned. The OAuth token exchange takes an injectable
httpx.Client for unit-testing without network.
"""
from __future__ import annotations

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


def _install_key(team_id: str, enterprise_id: str | None) -> str:
    return f"{enterprise_id or '-'}:{team_id}"


@dataclass
class InstallationStore:
    """Multi-workspace installation store (in-memory; swap for a SqlSlackInstallationStore in prod)."""
    _installs: dict[str, SlackInstallation] = field(default_factory=dict)

    def save(self, inst: SlackInstallation) -> None:
        # Bot token is encrypted at rest (Fernet); never stored in plaintext.
        self._installs[_install_key(inst.team_id, inst.enterprise_id)] = replace(
            inst, bot_token=encrypt(inst.bot_token))

    def fetch(self, team_id: str, enterprise_id: str | None = None) -> SlackInstallation | None:
        inst = self._installs.get(_install_key(team_id, enterprise_id))
        return replace(inst, bot_token=decrypt(inst.bot_token)) if inst else None

    def delete(self, team_id: str, enterprise_id: str | None = None) -> None:
        self._installs.pop(_install_key(team_id, enterprise_id), None)


@dataclass
class WorkspaceLinkStore:
    """Links a Slack (team_id, slack_user_id) to a Qiko worker/agent."""
    _links: dict[tuple[str, str], str] = field(default_factory=dict)

    def link(self, team_id: str, slack_user_id: str, worker_id: str) -> None:
        self._links[(team_id, slack_user_id)] = worker_id

    def resolve(self, team_id: str, slack_user_id: str) -> str | None:
        return self._links.get((team_id, slack_user_id))


class SlackOAuthError(Exception):
    pass


@dataclass
class SlackOAuth:
    store: InstallationStore
    client: httpx.Client | None = None

    def install_url(self, state: str) -> str:
        s = get_settings()
        params = {"client_id": s.slack_client_id, "scope": s.slack_scopes,
                  "redirect_uri": s.slack_redirect_uri, "state": state}
        return "https://slack.com/oauth/v2/authorize?" + urlencode(params)

    def exchange_code(self, code: str) -> SlackInstallation:
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
        self.store.save(inst)
        return inst
