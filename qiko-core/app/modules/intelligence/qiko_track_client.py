"""Thin async client for the Qiko Track v1 REST API.

Read-only: this module only issues GET requests. The connector is the only caller.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.modules.sales_intelligence.ssrf import SsrfError, assert_public_url


class QikoTrackClientError(Exception):
    """The API could not be reached or returned an unexpected shape."""


class QikoTrackClient:
    """Async client with injectable transport/resolver for testing and SSRF validation."""

    def __init__(self, base_url: str, token: str, *, transport=None, resolver=None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._validate_url(resolver)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            transport=transport,
            headers={"Accept": "application/json"},
            timeout=15.0,
        )

    def _validate_url(self, resolver) -> None:
        assert_public_url(self.base_url, resolver=resolver)
        parsed = urlparse(self.base_url)
        allowed = set(get_settings().qiko_track_api_allowlist or [])
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if allowed and origin not in allowed:
            raise SsrfError(f"host not in allowlist: {origin}")

    async def __aenter__(self) -> "QikoTrackClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.aclose()

    async def get_context(self) -> dict:
        return await self._get("/api/v1/context")

    async def list_tickets(self, *, project: str | None = None, limit: int = 200) -> list[dict]:
        params = {"limit": min(max(1, limit), 200)}
        if project:
            params["project"] = project
        body = await self._get("/api/v1/tickets", params=params)
        return body.get("tickets") or []

    async def get_ticket(self, key: str) -> dict:
        return await self._get(f"/api/v1/tickets/{key}")

    async def _get(self, path: str, params: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            response = await self._client.get(path, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise QikoTrackClientError(f"could not reach Qiko Track: {exc}") from exc
        try:
            body = response.json() if response.content else {}
        except json.JSONDecodeError as exc:
            raise QikoTrackClientError(
                f"Qiko Track returned non-JSON HTTP {response.status_code}") from exc
        if response.status_code == 401:
            raise QikoTrackClientError("token is invalid or expired")
        if response.status_code >= 400:
            message = body.get("error") or f"HTTP {response.status_code}"
            raise QikoTrackClientError(f"Qiko Track request failed: {message}")
        return body
