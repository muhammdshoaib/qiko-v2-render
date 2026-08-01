"""Transactional local-development tenant owner and platform Admin bootstrap."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import PlatformAdmin, Tenant, User
from app.modules.identity.admin_rbac import AdminRole
from app.modules.identity.rbac import Role
from app.modules.identity.security import hash_password


_TENANT_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class DevBootstrapError(Exception):
    """A fail-closed bootstrap error safe to show to a local operator."""


@dataclass(frozen=True)
class DevBootstrapResult:
    tenant_created: bool = False
    user_created: bool = False
    password_reset: bool = False
    owner_granted: bool = False
    super_admin_granted: bool = False
    tenant_updated: bool = False
    user_email_normalized: bool = False
    admin_email_normalized: bool = False

    @property
    def changes(self) -> int:
        return sum((
            self.tenant_created,
            self.user_created,
            self.password_reset,
            self.owner_granted,
            self.super_admin_granted,
            self.tenant_updated,
            self.user_email_normalized,
            self.admin_email_normalized,
        ))


def _normalize_inputs(
    tenant: str,
    display_name: str,
    email: str,
    password: str,
) -> tuple[str, str, str, str]:
    if not isinstance(tenant, str):
        raise DevBootstrapError("tenant must be a valid local identifier")
    tenant = tenant.strip()
    if not _TENANT_PATTERN.fullmatch(tenant):
        raise DevBootstrapError("tenant must be a valid local identifier")

    if not isinstance(display_name, str):
        raise DevBootstrapError("display name must not be blank")
    display_name = display_name.strip()
    if not display_name or len(display_name) > 255 or not display_name.isprintable():
        raise DevBootstrapError("display name must contain at most 255 printable characters")

    if not isinstance(email, str):
        raise DevBootstrapError("email must be a valid address")
    email = email.strip().lower()
    local, separator, domain = email.partition("@")
    if (
        len(email) > 320
        or email.count("@") != 1
        or not separator
        or not local
        or not domain
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
        or any(character.isspace() or ord(character) < 32 for character in email)
    ):
        raise DevBootstrapError("email must be a valid address")

    if (
        not isinstance(password, str)
        or len(password) < 8
        or len(password) > 256
        or not password.strip()
        or any(ord(character) < 32 for character in password)
    ):
        raise DevBootstrapError("password must contain between 8 and 256 characters")
    return tenant, display_name, email, password


async def bootstrap_dev_admin(
    sessionmaker: async_sessionmaker[AsyncSession],
    tenant: str,
    display_name: str,
    email: str,
    password: str,
    reset_password: bool = False,
) -> DevBootstrapResult:
    tenant, display_name, email, password = _normalize_inputs(
        tenant,
        display_name,
        email,
        password,
    )
    if not isinstance(reset_password, bool):
        raise DevBootstrapError("reset_password must be a boolean")

    async with sessionmaker() as session, session.begin():
        apply_locks = session.bind is not None and session.bind.dialect.name == "postgresql"
        if apply_locks:
            for lock_key in sorted((f"email:{email}", f"tenant:{tenant}")):
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": lock_key},
                )

        tenant_row = await session.get(Tenant, tenant, with_for_update=apply_locks)

        user_query = select(User).where(func.lower(User.email) == email)
        admin_query = select(PlatformAdmin).where(func.lower(PlatformAdmin.email) == email)
        if apply_locks:
            user_query = user_query.with_for_update()
            admin_query = admin_query.with_for_update()
        users = (await session.execute(user_query)).scalars().all()
        admins = (await session.execute(admin_query)).scalars().all()
        if len(users) > 1 or len(admins) > 1:
            raise DevBootstrapError("multiple existing records match the normalized email")

        user_row = users[0] if users else None
        admin_row = admins[0] if admins else None
        if user_row is not None and user_row.tenant_id != tenant:
            raise DevBootstrapError("the user email belongs to another tenant")

        tenant_created = tenant_row is None
        tenant_updated = tenant_row is not None and tenant_row.name != display_name
        user_created = user_row is None
        owner_granted = user_row is None or user_row.role != Role.owner.value
        password_reset = user_row is not None and reset_password
        super_admin_granted = admin_row is None or admin_row.role != AdminRole.super_admin.value
        user_email_normalized = user_row is not None and user_row.email != email
        admin_email_normalized = admin_row is not None and admin_row.email != email

        if tenant_row is None:
            session.add(Tenant(id=tenant, name=display_name))
        elif tenant_updated:
            tenant_row.name = display_name

        if user_row is None:
            session.add(User(
                id=uuid.uuid4().hex[:12],
                email=email,
                password_hash=hash_password(password),
                tenant_id=tenant,
                role=Role.owner.value,
            ))
        else:
            if user_email_normalized:
                user_row.email = email
            if owner_granted:
                user_row.role = Role.owner.value
            if password_reset:
                user_row.password_hash = hash_password(password)

        if admin_row is None:
            session.add(PlatformAdmin(email=email, role=AdminRole.super_admin.value))
        else:
            if admin_email_normalized:
                admin_row.email = email
            if super_admin_granted:
                admin_row.role = AdminRole.super_admin.value

        await session.flush()
        return DevBootstrapResult(
            tenant_created=tenant_created,
            user_created=user_created,
            password_reset=password_reset,
            owner_granted=owner_granted,
            super_admin_granted=super_admin_granted,
            tenant_updated=tenant_updated,
            user_email_normalized=user_email_normalized,
            admin_email_normalized=admin_email_normalized,
        )
