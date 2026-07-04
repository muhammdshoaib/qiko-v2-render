"""Channel session store: links a channel identity (phone/Slack user) to a Qiko worker.

Tokens are ENCRYPTED at rest (crypto.py), sessions expire after a TTL, and everything is
tenant-scoped - fixing the legacy plaintext + unbounded session stores.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.crypto import decrypt, encrypt

DEFAULT_TTL = 7 * 24 * 3600  # 7 days


@dataclass
class ChannelSession:
    tenant: str
    external_id: str
    enc_token: str | None = None       # encrypted at rest
    selected_worker: str | None = None
    reply_mode: str = "text"           # text | voice
    expires_at: float = 0.0


@dataclass
class ChannelSessionStore:
    ttl_seconds: int = DEFAULT_TTL
    _sessions: dict[tuple[str, str], ChannelSession] = field(default_factory=dict)

    def _now(self) -> float:
        return time.monotonic()

    def _key(self, tenant: str, external_id: str) -> tuple[str, str]:
        return (tenant, external_id)

    def get(self, tenant: str, external_id: str) -> ChannelSession | None:
        s = self._sessions.get(self._key(tenant, external_id))
        if s and s.expires_at and s.expires_at < self._now():
            self._sessions.pop(self._key(tenant, external_id), None)  # expired
            return None
        return s

    def _touch(self, tenant: str, external_id: str) -> ChannelSession:
        s = self.get(tenant, external_id) or ChannelSession(tenant=tenant, external_id=external_id)
        s.expires_at = self._now() + self.ttl_seconds
        self._sessions[self._key(tenant, external_id)] = s
        return s

    def set_token(self, tenant: str, external_id: str, token: str) -> None:
        s = self._touch(tenant, external_id)
        s.enc_token = encrypt(token)  # never stored in plaintext

    def get_token(self, tenant: str, external_id: str) -> str | None:
        s = self.get(tenant, external_id)
        return decrypt(s.enc_token) if s and s.enc_token else None

    def select_worker(self, tenant: str, external_id: str, worker: str) -> None:
        self._touch(tenant, external_id).selected_worker = worker

    def set_reply_mode(self, tenant: str, external_id: str, mode: str) -> None:
        if mode not in {"text", "voice"}:
            raise ValueError("reply_mode must be text or voice")
        self._touch(tenant, external_id).reply_mode = mode
