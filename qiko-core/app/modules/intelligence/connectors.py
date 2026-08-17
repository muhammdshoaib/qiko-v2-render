"""Read-only source connectors for the Intelligence Worker.

Each connector implements the `Connector` Protocol from `app.modules.intelligence.catalog`.
Nothing here writes to the third party; `verify()` performs read-only checks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.modules.intelligence.models import Signal


@dataclass
class GitHubConnector:
    """Read-only GitHub connector: verify token and repo allowlist."""

    key: str = "github"
    _base: str = "https://api.github.com"

    async def fetch_since(self, *, config: dict, credential: str,
                          since: Any) -> list[Signal]:
        """Poll connector; not used until the GitHub scheduler milestone."""
        raise NotImplementedError("GitHub fetch is not implemented yet")

    async def verify(self, *, config: dict, credential: str) -> dict:
        if not credential:
            return {"ok": False, "error": "GitHub token is required"}

        headers = {"Authorization": f"Bearer {credential}", "Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient(base_url=self._base, headers=headers, timeout=15.0) as client:
            user_resp = await client.get("/user")
            if user_resp.status_code == 401:
                return {"ok": False, "error": "GitHub token is invalid or expired"}
            user_resp.raise_for_status()
            user = user_resp.json()
            login = user.get("login", "")

            allowlist = config.get("repo_allowlist") or []
            repo_results = []
            missing = []
            for repo in allowlist:
                if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo):
                    missing.append(f"{repo} is not a valid owner/repo")
                    continue
                r = await client.get(f"/repos/{repo}")
                if r.status_code == 404:
                    missing.append(f"{repo} not found or not accessible")
                elif r.status_code == 200:
                    data = r.json()
                    repo_results.append({
                        "full_name": data.get("full_name"),
                        "private": data.get("private"),
                    })
                else:
                    missing.append(f"{repo}: HTTP {r.status_code}")

            return {
                "ok": True,
                "user": login,
                "repos": repo_results,
                "errors": missing if missing else None,
            }


@dataclass
class QikoTrackConnector:
    """Qiko Track connector placeholder.

    The v1 REST API contract is still being finalised (see
    `.devin/specs/2026-08-15-qiko-track-api-requirements-for-intelligence-worker.md`), so this
    connector stores the credential and reports an actionable "not yet" status instead of failing
    silently or guessing at endpoints.
    """

    key: str = "qiko_track"

    async def fetch_since(self, *, config: dict, credential: str,
                          since: Any) -> list[Signal]:
        """Poll connector; not used until the Qiko Track scheduler milestone."""
        raise NotImplementedError("Qiko Track fetch is not implemented yet")

    async def verify(self, *, config: dict, credential: str) -> dict:
        return {
            "ok": False,
            "error": (
                "Qiko Track connector is not implemented yet; "
                "the token and project key are saved and will be used when the connector lands."),
        }
