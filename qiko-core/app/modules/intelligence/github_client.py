"""Read-only GitHub client for the Intelligence Worker.

Supports both personal access tokens and GitHub App installation tokens (minted
per request from the App ID and private key in Settings). All outbound URLs are
validated against the configured allowlist and public-IP SSRF rules.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt

from app.core.config import get_settings
from app.modules.intelligence.discrepancies import _extract_refs
from app.modules.intelligence.models import Signal
from app.modules.sales_intelligence.ssrf import SsrfError, assert_public_url

logger = logging.getLogger(__name__)

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubClientError(Exception):
    """The GitHub API could not be reached or returned an unexpected shape."""


class GitHubRateLimitError(GitHubClientError):
    """Hit the GitHub rate limit despite a small backoff window."""


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _fmt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


class GitHubClient:
    """Async GitHub client with SSRF-safe custom base URL and rate-limit backoff."""

    def __init__(self, credential: str, *, base_url: str | None = None,
                 transport: Any | None = None, resolver: Any | None = None) -> None:
        self.credential = credential.strip()
        settings = get_settings()
        self.base_url = (base_url or settings.github_api_base).rstrip("/")
        self._transport = transport
        self._resolver = resolver
        self._validate_url()
        self._installation_token: str | None = None
        self._installation_token_expires: float = 0.0

    def _validate_url(self) -> None:
        assert_public_url(self.base_url, resolver=self._resolver)
        parsed = urlparse(self.base_url)
        allowed = set(get_settings().github_api_allowlist or [])
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if allowed and origin not in allowed:
            raise SsrfError(f"host not in allowlist: {origin}")

    @property
    def _is_installation_id(self) -> bool:
        return self.credential.isdigit()

    async def _token(self) -> str:
        if not self._is_installation_id:
            return self.credential
        if self._installation_token and time.time() < self._installation_token_expires - 60:
            return self._installation_token
        self._installation_token = await self._mint_installation_token()
        self._installation_token_expires = time.time() + 3300
        return self._installation_token

    def _mint_app_jwt(self) -> str:
        settings = get_settings()
        app_id = settings.github_app_id
        private_key = settings.github_app_private_key
        if not app_id or not private_key:
            raise GitHubClientError("GitHub App is not configured")
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 600,
            "iss": app_id,
        }
        try:
            return jwt.encode(payload, private_key, algorithm="RS256")
        except Exception as exc:
            raise GitHubClientError(f"failed to mint GitHub App JWT: {exc}") from exc

    async def _mint_installation_token(self) -> str:
        app_token = self._mint_app_jwt()
        path = f"/app/installations/{self.credential}/access_tokens"
        result = await self._request("POST", path, token=app_token, retry_on_rate_limit=False)
        token = result.get("token")
        if not token:
            raise GitHubClientError("GitHub App did not return an installation token")
        return token

    async def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                       token: str | None = None, retry_on_rate_limit: bool = True) -> Any:
        auth_token = token or await self._token()
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {auth_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(
            base_url=self.base_url,
            transport=self._transport,
            timeout=30.0,
        ) as client:
            for attempt in range(3):
                try:
                    response = await client.request(method, path, params=params, headers=headers)
                except httpx.HTTPError as exc:
                    raise GitHubClientError(f"could not reach GitHub: {exc}") from exc

                if response.status_code == 401:
                    raise GitHubClientError("GitHub token is invalid or expired")
                if response.status_code == 403:
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    if remaining == "0" and retry_on_rate_limit:
                        reset = int(response.headers.get("X-RateLimit-Reset", 0) or 0)
                        wait = max(0, min(reset - time.time(), 60))
                        if wait > 0 and attempt < 2:
                            await asyncio.sleep(wait)
                            continue
                    raise GitHubRateLimitError("GitHub rate limit exceeded")
                response.raise_for_status()
                if response.status_code == 204:
                    return {}
                try:
                    return response.json()
                except Exception as exc:
                    raise GitHubClientError(f"GitHub returned non-JSON: {exc}") from exc
        raise GitHubRateLimitError("GitHub rate limit persisted after backoff")

    async def verify(self, repo_allowlist: list[str]) -> dict:
        """Check the credential and repo visibility. Returns a summary dict."""
        try:
            if self._is_installation_id:
                user_or_app = await self._request(
                    "GET", f"/app/installations/{self.credential}", token=self._mint_app_jwt())
            else:
                user_or_app = await self._request("GET", "/user")
        except GitHubClientError as exc:
            return {"ok": False, "error": str(exc)}

        login = user_or_app.get("account", {}).get("login") or user_or_app.get("login") or user_or_app.get("slug", "app")
        repo_results = []
        missing = []
        for repo in repo_allowlist:
            if not _REPO_RE.match(repo):
                missing.append(f"{repo} is not a valid owner/repo")
                continue
            try:
                data = await self._request("GET", f"/repos/{repo}")
                repo_results.append({"full_name": data.get("full_name"), "private": data.get("private")})
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if hasattr(exc, "response") else 0
                if status == 404:
                    missing.append(f"{repo} not found or not accessible")
                else:
                    missing.append(f"{repo}: HTTP {status}")
            except GitHubClientError as exc:
                missing.append(f"{repo}: {exc}")

        return {
            "ok": True,
            "user": login,
            "repos": repo_results,
            "errors": missing if missing else None,
        }

    async def fetch_signals(self, *, config: dict, since: datetime | None,
                            tenant: str, agent_id: str) -> list[Signal]:
        """Poll repos for PRs, reviews, check runs and commits."""
        if since is None:
            since = datetime.min.replace(tzinfo=timezone.utc)
        repos = config.get("repo_allowlist") or []
        watched_branches = config.get("watched_branches") or []
        signals: list[Signal] = []
        for repo in repos:
            if not _REPO_RE.match(repo):
                logger.warning("invalid repo allowlist entry: %s", repo)
                continue
            signals.extend(await self._fetch_repo_signals(
                repo, since, tenant, agent_id, watched_branches))
        return signals

    async def _fetch_repo_signals(self, repo: str, since: datetime, tenant: str,
                                  agent_id: str, watched_branches: list[str]) -> list[Signal]:
        signals: list[Signal] = []
        page = 1
        while True:
            pulls = await self._request("GET", f"/repos/{repo}/pulls", params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": "100",
                "page": str(page),
            })
            if not isinstance(pulls, list):
                break
            if not pulls:
                break
            stopped = True
            for pr in pulls:
                updated = _parse_iso(pr.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)
                if updated < since:
                    continue
                stopped = False
                signals.extend(self._pr_signals(pr, repo, tenant, agent_id, since))
                signals.extend(await self._pr_reviews_and_checks(repo, pr, since, tenant, agent_id))
            if stopped or len(pulls) < 100:
                break
            page += 1

        for branch in watched_branches:
            signals.extend(await self._fetch_commits(repo, branch, since, tenant, agent_id))
        return signals

    async def _fetch_commits(self, repo: str, branch: str, since: datetime,
                             tenant: str, agent_id: str) -> list[Signal]:
        params: dict[str, Any] = {"sha": branch, "per_page": "100"}
        since_str = _fmt_iso(since)
        if since_str:
            params["since"] = since_str
        commits = await self._request("GET", f"/repos/{repo}/commits", params=params)
        if not isinstance(commits, list):
            return []
        signals: list[Signal] = []
        for commit in commits:
            sha = commit.get("sha", "")[:12]
            message = (commit.get("commit") or {}).get("message", "")
            git_author = (commit.get("commit") or {}).get("author") or {}
            git_name = git_author.get("name", "")
            actor = (commit.get("author") or {}).get("login") or git_name
            date = _parse_iso(git_author.get("date"))
            url = commit.get("html_url") or f"https://github.com/{repo}/commit/{sha}"
            ref = self._ref_from_text(message, branch)
            signals.append(Signal(
                tenant=tenant,
                agent_id=agent_id,
                source="github",
                kind="commit",
                external_id=f"commit-{sha}",
                title=f"{repo}@{branch}: {message.splitlines()[0] if message else 'commit'}",
                body=message,
                actor=actor,
                url=url,
                ref=ref,
                container=repo,
                occurred_at=date,
                meta={
                    "git_author_name": git_name,
                    "git_author_email": git_author.get("email", ""),
                },
            ))
        return signals

    def _pr_signals(self, pr: dict[str, Any], repo: str, tenant: str, agent_id: str,
                    since: datetime) -> list[Signal]:
        signals: list[Signal] = []
        number = pr.get("number")
        title = pr.get("title", "")
        body = pr.get("body") or ""
        head_ref = pr.get("head", {}).get("ref", "")
        user = pr.get("user", {}) or {}
        actor = user.get("login", "")
        url = pr.get("html_url", "")
        state = pr.get("state", "")
        created_at = _parse_iso(pr.get("created_at"))
        updated_at = _parse_iso(pr.get("updated_at"))
        closed_at = _parse_iso(pr.get("closed_at"))
        merged_at = _parse_iso(pr.get("merged_at"))
        merged = pr.get("merged", False) or merged_at is not None
        draft = pr.get("draft", False)
        ref = self._ref_from_text(f"{title} {body}", head_ref)

        if created_at and created_at >= since:
            signals.append(Signal(
                tenant=tenant, agent_id=agent_id, source="github", kind="pr_opened",
                external_id=f"pr-{number}", title=title, body=body, actor=actor,
                url=url, ref=ref, container=repo, occurred_at=created_at,
            ))

        if merged and merged_at and merged_at >= since:
            signals.append(Signal(
                tenant=tenant, agent_id=agent_id, source="github", kind="pr_merged",
                external_id=f"pr-{number}-merged", title=f"Merged: {title}",
                body=body, actor=actor, url=url, ref=ref, container=repo, occurred_at=merged_at,
            ))

        if state == "closed" and not merged and closed_at and closed_at >= since:
            signals.append(Signal(
                tenant=tenant, agent_id=agent_id, source="github", kind="pr_closed",
                external_id=f"pr-{number}-closed", title=f"Closed: {title}",
                body=body, actor=actor, url=url, ref=ref, container=repo, occurred_at=closed_at,
            ))

        if state == "open" and not draft:
            requested = (pr.get("requested_reviewers") or []) + (pr.get("requested_teams") or [])
            if requested:
                occurred = created_at or updated_at
                signals.append(Signal(
                    tenant=tenant, agent_id=agent_id, source="github", kind="review_requested",
                    external_id=f"pr-{number}-requested", title=f"Review requested: {title}",
                    body=body, actor=actor, url=url, ref=ref, container=repo, occurred_at=occurred,
                ))

        # Reviews and check runs are fetched async; return core signals here and rely on
        # follow-up calls in _fetch_repo_signals. Because SignalStore dedupes, we can re-emit
        # the same PR signals while adding review/check details on each poll.
        return signals

    async def _pr_reviews_and_checks(self, repo: str, pr: dict[str, Any], since: datetime,
                                     tenant: str, agent_id: str) -> list[Signal]:
        """Fetch reviews and latest check run for a PR. Called after _pr_signals."""
        signals: list[Signal] = []
        number = pr.get("number")
        title = pr.get("title", "")
        body = pr.get("body") or ""
        head_ref = pr.get("head", {}).get("ref", "")
        ref = self._ref_from_text(f"{title} {body}", head_ref)
        url = pr.get("html_url", "")
        head_sha = pr.get("head", {}).get("sha", "")

        reviews = await self._request("GET", f"/repos/{repo}/pulls/{number}/reviews")
        if isinstance(reviews, list):
            approvals = [r for r in reviews if r.get("state") == "APPROVED"]
            if approvals:
                latest = max(approvals, key=lambda r: _parse_iso(r.get("submitted_at")) or since)
                submitted = _parse_iso(latest.get("submitted_at"))
                if submitted and submitted >= since:
                    signals.append(Signal(
                        tenant=tenant, agent_id=agent_id, source="github", kind="review_approved",
                        external_id=f"pr-{number}-approved",
                        title=f"Approved: {title}",
                        body=f"Approved by {latest.get('user', {}).get('login', '')}",
                        actor=latest.get("user", {}).get("login", ""),
                        url=url, ref=ref, container=repo, occurred_at=submitted,
                    ))
            re_request = [r for r in reviews if r.get("state") == "CHANGES_REQUESTED"]
            if re_request:
                latest = max(re_request, key=lambda r: _parse_iso(r.get("submitted_at")) or since)
                submitted = _parse_iso(latest.get("submitted_at"))
                if submitted and submitted >= since:
                    signals.append(Signal(
                        tenant=tenant, agent_id=agent_id, source="github",
                        kind="review_changes_requested",
                        external_id=f"pr-{number}-changes",
                        title=f"Changes requested: {title}",
                        body=f"Changes requested by {latest.get('user', {}).get('login', '')}",
                        actor=latest.get("user", {}).get("login", ""),
                        url=url, ref=ref, container=repo, occurred_at=submitted,
                    ))

        if head_sha:
            checks = await self._request("GET", f"/repos/{repo}/commits/{head_sha}/check-runs")
            if isinstance(checks, dict):
                for run in checks.get("check_runs") or []:
                    if run.get("status") != "completed":
                        continue
                    conclusion = run.get("conclusion")
                    completed = _parse_iso(run.get("completed_at"))
                    if conclusion == "failure" and completed and completed >= since:
                        signals.append(Signal(
                            tenant=tenant, agent_id=agent_id, source="github", kind="ci_failed",
                            external_id=f"pr-{number}-check-{run.get('id')}",
                            title=f"CI failed: {run.get('name', 'check')}",
                            body=f"Check run `{run.get('name')}` failed for {repo}#{number}",
                            actor=run.get("app", {}).get("name", ""),
                            url=run.get("html_url") or url, ref=ref, container=repo,
                            occurred_at=completed,
                        ))
        return signals

    def _ref_from_text(self, text: str, branch: str) -> str | None:
        refs = _extract_refs(text)
        if not refs and branch:
            refs = _extract_refs(branch)
        return refs[0] if refs else None
