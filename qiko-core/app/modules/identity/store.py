"""User store. In-memory implementation stands in until the DB-backed store lands with the
data-migration work (SCRUM-7). The rest of the module depends only on the UserStore protocol."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.identity.rbac import Role
from app.modules.identity import twofa
from app.modules.identity.security import hash_password, verify_password


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    tenant: str | None = None
    role: Role = Role.viewer
    twofa_enabled: bool = False
    totp_secret: str | None = None
    current_sid: str | None = None


class UserStore(Protocol):
    async def add(self, user: User) -> User: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: str) -> User | None: ...
    async def list_by_tenant(self, tenant: str) -> list[User]: ...
    async def set_sid(self, user_id: str, sid: str | None) -> None: ...
    async def enable_twofa(self, user_id: str, secret: str,
                           backup_code_hashes: dict[str, str] | None = None) -> None: ...
    async def consume_backup_code(self, user_id: str, code: str) -> bool: ...
    async def set_password(self, user_id: str, password_hash: str) -> None: ...
    async def set_role(self, user_id: str, role: Role) -> None: ...
    async def delete(self, user_id: str) -> None: ...


@dataclass
class InMemoryUserStore:
    _by_id: dict[str, User] = field(default_factory=dict)
    _backup_codes: dict[str, dict[str, str]] = field(default_factory=dict)

    def seed(self, user: User) -> User:
        """Synchronous bootstrap insert (dev seeding / tests). Runtime writes use async add()."""
        self._by_id[user.id] = user
        return user

    async def add(self, user: User) -> User:
        return self.seed(user)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._by_id.values() if u.email == email.lower()), None)

    async def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    async def list_by_tenant(self, tenant: str) -> list[User]:
        return [u for u in self._by_id.values() if u.tenant == tenant]

    async def set_sid(self, user_id: str, sid: str | None) -> None:
        user = self._by_id.get(user_id)
        if user:
            user.current_sid = sid

    async def enable_twofa(self, user_id: str, secret: str,
                           backup_code_hashes: dict[str, str] | None = None) -> None:
        user = self._by_id.get(user_id)
        if user:
            user.twofa_enabled = True
            user.totp_secret = secret
            self._backup_codes[user_id] = dict(backup_code_hashes or {})

    async def consume_backup_code(self, user_id: str, code: str) -> bool:
        selector = twofa.backup_code_selector(code)
        encoded = self._backup_codes.get(user_id, {}).get(selector or "")
        if not selector or not encoded or not verify_password(twofa.normalize_backup_code(code), encoded):
            return False
        del self._backup_codes[user_id][selector]
        return True

    async def set_password(self, user_id: str, password_hash: str) -> None:
        user = self._by_id.get(user_id)
        if user:
            user.password_hash = password_hash

    async def set_role(self, user_id: str, role: Role) -> None:
        user = self._by_id.get(user_id)
        if user:
            user.role = role

    async def delete(self, user_id: str) -> None:
        self._by_id.pop(user_id, None)
        self._backup_codes.pop(user_id, None)


def seeded_store() -> InMemoryUserStore:
    """An in-memory store. Seeds a dev owner account ONLY in debug/dev, so no default credentials
    ever ship to preprod/live (A07). Prod bootstraps its admin from SSM secrets / migration."""
    from app.core.config import get_settings

    store = InMemoryUserStore()
    if get_settings().debug:
        store.seed(User(id="u-owner", email="owner" + "@" + "qiko.ai",
                        password_hash=hash_password("change-me-locally"),
                        tenant="qiko", role=Role.owner))
    return store
