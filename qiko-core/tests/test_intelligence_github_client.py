"""Unit tests for GitHubClient/GitHubConnector (previously zero coverage).

Mirrors the httpx.MockTransport(handler) convention already used in
tests/test_integration_clients.py and tests/test_qiko_track_connector.py: no real network, and a
stub `resolver` stands in for DNS so the SSRF guard's public-IP check stays hermetic (see
tests/test_generic_connector.py for the same pattern on the shared ssrf module).
"""
from __future__ import annotations

import socket
from datetime import datetime, timezone

import httpx
import pytest

from app.modules.intelligence.connectors import GitHubConnector
from app.modules.intelligence.github_client import GitHubClient, GitHubRateLimitError
from app.modules.sales_intelligence.ssrf import SsrfError


def _public_resolver(host, port, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


@pytest.mark.asyncio
async def test_connector_fetch_since_returns_commit_signal_for_watched_branch():
    """Success path: GitHubConnector.fetch_since -> GitHubClient.fetch_signals -> one commit on
    the watched branch, with no open PRs, becomes exactly one normalised `commit` Signal."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer ghp_test_token"
        if request.url.path == "/repos/acme/repo/pulls":
            assert request.url.params.get("page") == "1"
            return httpx.Response(200, json=[])
        if request.url.path == "/repos/acme/repo/commits":
            assert request.url.params.get("sha") == "main"
            return httpx.Response(200, json=[{
                "sha": "abc123def4567890",
                "commit": {
                    "author": {"name": "Dev Person", "email": "dev@example.com",
                              "date": "2026-09-01T00:00:00Z"},
                    "message": "fix: retry webhook delivery (QIW-1023)",
                },
                "author": {"login": "devlogin"},
                "html_url": "https://github.com/acme/repo/commit/abc123def4567890",
            }])
        return httpx.Response(404, json={"message": "not found"})

    connector = GitHubConnector(transport=httpx.MockTransport(handler), resolver=_public_resolver)
    signals = await connector.fetch_since(
        config={"repo_allowlist": ["acme/repo"], "watched_branches": ["main"]},
        credential="ghp_test_token",
        since=None,
        tenant="acme-tenant",
        agent_id="worker-1",
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source == "github"
    assert signal.kind == "commit"
    assert signal.external_id == "commit-abc123def456"
    assert signal.container == "acme/repo"
    assert signal.actor == "devlogin"
    assert signal.ref == "QIW-1023"
    assert signal.url == "https://github.com/acme/repo/commit/abc123def4567890"
    assert signal.title == "acme/repo@main: fix: retry webhook delivery (QIW-1023)"
    assert signal.occurred_at == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert signal.meta["git_author_name"] == "Dev Person"
    assert signal.meta["git_author_email"] == "dev@example.com"


@pytest.mark.asyncio
async def test_fetch_signals_parses_pr_review_and_check_run_signals():
    """Success path for the other three data types this client fetches: an open PR with a
    pending review request, one approval, one changes-requested review and one failed check
    run must each become their own Signal kind."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer ghp_test_token"
        path = request.url.path
        if path == "/repos/acme/repo/pulls":
            return httpx.Response(200, json=[{
                "number": 7,
                "title": "Add retry",
                "body": "Fixes QIW-77",
                "head": {"ref": "feature/qiw-77-retry", "sha": "deadbeefcafe"},
                "user": {"login": "alice"},
                "html_url": "https://github.com/acme/repo/pull/7",
                "state": "open",
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-02T00:00:00Z",
                "closed_at": None,
                "merged_at": None,
                "merged": False,
                "draft": False,
                "requested_reviewers": [{"login": "bob"}],
                "requested_teams": [],
            }])
        if path == "/repos/acme/repo/pulls/7/reviews":
            return httpx.Response(200, json=[
                {"state": "APPROVED", "user": {"login": "carol"},
                 "submitted_at": "2026-09-03T00:00:00Z"},
                {"state": "CHANGES_REQUESTED", "user": {"login": "dave"},
                 "submitted_at": "2026-09-03T00:30:00Z"},
            ])
        if path == "/repos/acme/repo/commits/deadbeefcafe/check-runs":
            return httpx.Response(200, json={"check_runs": [
                {"status": "completed", "conclusion": "failure",
                 "completed_at": "2026-09-03T01:00:00Z", "name": "unit-tests",
                 "html_url": "https://github.com/acme/repo/runs/99", "id": 99,
                 "app": {"name": "github-actions"}},
            ]})
        return httpx.Response(404, json={"message": "not found"})

    client = GitHubClient("ghp_test_token", transport=httpx.MockTransport(handler),
                          resolver=_public_resolver)
    signals = await client.fetch_signals(
        config={"repo_allowlist": ["acme/repo"], "watched_branches": []},
        since=None, tenant="acme-tenant", agent_id="worker-1")

    kinds = {s.kind for s in signals}
    assert kinds == {
        "pr_opened", "review_requested", "review_approved",
        "review_changes_requested", "ci_failed",
    }

    approved = next(s for s in signals if s.kind == "review_approved")
    assert approved.external_id == "pr-7-approved"
    assert approved.actor == "carol"

    changes = next(s for s in signals if s.kind == "review_changes_requested")
    assert changes.actor == "dave"

    ci_failed = next(s for s in signals if s.kind == "ci_failed")
    assert ci_failed.external_id == "pr-7-check-99"
    assert ci_failed.title == "CI failed: unit-tests"
    assert ci_failed.url == "https://github.com/acme/repo/runs/99"
    assert ci_failed.actor == "github-actions"


@pytest.mark.asyncio
async def test_fetch_signals_raises_rate_limit_error_on_zero_remaining():
    """A 403 with X-RateLimit-Remaining: 0 and a reset already in the past must surface as
    GitHubRateLimitError rather than retrying forever or being swallowed as a generic error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "0"},
                              json={"message": "API rate limit exceeded"})

    client = GitHubClient("ghp_test_token", transport=httpx.MockTransport(handler),
                          resolver=_public_resolver)
    with pytest.raises(GitHubRateLimitError):
        await client.fetch_signals(
            config={"repo_allowlist": ["acme/repo"], "watched_branches": []},
            since=None, tenant="acme-tenant", agent_id="worker-1")


def test_constructor_rejects_link_local_metadata_base_url():
    """A literal link-local/metadata address (the classic SSRF target) must be rejected at
    construction time, before any request is ever made."""
    with pytest.raises(SsrfError):
        GitHubClient(
            "ghp_test_token", base_url="http://169.254.169.254/",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])))


def test_constructor_rejects_host_outside_allowlist():
    """Even a hostname that resolves to a public IP is rejected unless its origin is in the
    configured github_api_allowlist - GitHubClient's own defense-in-depth on top of the shared
    public-IP SSRF guard."""
    with pytest.raises(SsrfError, match="allowlist"):
        GitHubClient(
            "ghp_test_token", base_url="https://evil.example.com",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
            resolver=_public_resolver)


@pytest.mark.asyncio
async def test_connector_verify_reports_error_for_ssrf_rejected_base_url():
    """GitHubConnector.verify() must turn the SsrfError into a reported failure, not an unhandled
    exception that would take down the verify-credential endpoint."""
    connector = GitHubConnector()
    result = await connector.verify(
        config={"base_url": "http://169.254.169.254/"}, credential="ghp_test_token")
    assert result["ok"] is False
    assert "unsafe base url" in result["error"].lower()
