"""Thin async client for the Qiko Track v1 REST API.

Read-only calls back the connector; the human-approved backlog proposal path uses
`create_ticket` directly.
"""
from __future__ import annotations

import json
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.modules.sales_intelligence.ssrf import SsrfError, assert_public_url


class QikoTrackClientError(Exception):
    """The API could not be reached or returned an unexpected shape."""


class QikoTrackClient:
    """Async client with injectable transport/resolver for testing and SSRF validation."""

    def __init__(self, base_url: str, token: str, *, transport: Any | None = None,
                 resolver: Any | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._transport = transport
        self._resolver = resolver or socket.getaddrinfo
        self._validate_url()

    def _validate_url(self) -> None:
        assert_public_url(self.base_url, resolver=self._resolver)
        parsed = urlparse(self.base_url)
        allowed = set(get_settings().qiko_track_api_allowlist or [])
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if allowed and origin not in allowed:
            raise SsrfError(f"host not in allowlist: {origin}")

    async def get_context(self) -> dict:
        return await self._request("GET", "/api/v1/context")

    async def list_tickets(self, *, project: str | None = None, limit: int = 200) -> list[dict]:
        params: dict[str, Any] = {"limit": min(max(1, limit), 200)}
        if project:
            params["project"] = project
        body = await self._request("GET", "/api/v1/tickets", params=params)
        return body.get("tickets") or []

    async def get_ticket(self, key: str) -> dict:
        return await self._request("GET", f"/api/v1/tickets/{key}")

    async def get_metrics(self, project_key: str, *, window: str = "30d",
                          sprint: int | None = None) -> dict:
        params: dict[str, Any] = {"window": window}
        if sprint is not None:
            params["sprint"] = sprint
        return await self._request(
            "GET", f"/api/v1/projects/{project_key}/metrics", params=params)

    async def create_ticket(self, payload: dict, *, idempotency_key: str | None = None) -> dict:
        headers: dict[str, str] = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return await self._request("POST", "/api/v1/tickets", json_payload=payload, headers=headers)

    async def _request(self, method: str, path: str, params: dict | None = None,
                       json_payload: dict | None = None, headers: dict[str, str] | None = None) -> dict:
        default_headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        if headers:
            default_headers.update(headers)
        async with httpx.AsyncClient(
            base_url=self.base_url,
            transport=self._transport,
            timeout=15.0,
        ) as client:
            try:
                response = await client.request(
                    method, path, params=params, json=json_payload, headers=default_headers)
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
