"""Validated, transactional tenant provisioning over the application ORM models."""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Agent as AgentRow
from app.db.models import Tenant as TenantRow
from app.db.models import User as UserRow
from app.modules.agents.service import AGENT_STATUSES, AGENT_TYPES
from app.modules.identity.rbac import Role
from app.modules.identity.security import hash_password


class ProvisioningError(Exception):
    """A fail-closed provisioning precondition error safe to show to an operator."""


class StrictManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ManifestTenant(StrictManifestModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
    display_name: str = Field(min_length=1, max_length=255)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("display_name must not be blank")
        return value


class ManifestUser(StrictManifestModel):
    email: str = Field(min_length=3, max_length=320)
    role: str

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        local, separator, domain = value.partition("@")
        if (
            not separator
            or not local
            or not domain
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
            or any(character.isspace() or ord(character) < 32 for character in value)
        ):
            raise ValueError("email must be a valid address")
        return value

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {role.value for role in Role}:
            raise ValueError("role is not supported")
        return value


class ManifestAgent(StrictManifestModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
    name: str = Field(min_length=1, max_length=255)
    atype: str
    status: str
    config: dict = Field()

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("atype")
    @classmethod
    def validate_atype(cls, value: str) -> str:
        if value not in AGENT_TYPES:
            raise ValueError("atype is not supported")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in AGENT_STATUSES:
            raise ValueError("status is not supported")
        return value


class TenantManifest(StrictManifestModel):
    tenant: ManifestTenant
    users: list[ManifestUser] = Field(max_length=1000)
    agents: list[ManifestAgent] = Field(max_length=1000)

    @model_validator(mode="after")
    def reject_duplicates(self) -> TenantManifest:
        emails = [user.email for user in self.users]
        if len(emails) != len(set(emails)):
            raise ValueError("manifest user emails must be unique")
        agent_ids = [agent.id for agent in self.agents]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("manifest agent ids must be unique")
        return self


@dataclass(frozen=True)
class ProvisioningResult:
    tenant: str
    tenants_created: int = 0
    tenants_updated: int = 0
    users_created: int = 0
    users_updated: int = 0
    passwords_reset: int = 0
    agents_created: int = 0
    agents_updated: int = 0

    @property
    def changes(self) -> int:
        return (
            self.tenants_created
            + self.tenants_updated
            + self.users_created
            + self.users_updated
            + self.agents_created
            + self.agents_updated
        )


@dataclass
class _UserChange:
    desired: ManifestUser
    row: UserRow | None
    password_hash: str | None
    role_changed: bool


@dataclass
class _AgentChange:
    desired: ManifestAgent
    row: AgentRow | None
    merged_config: dict
    changed: bool


async def provision_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
    manifest: TenantManifest,
    *,
    reset_existing_passwords: bool,
    apply: bool,
) -> ProvisioningResult:
    """Preflight the complete manifest, then optionally apply every change in one transaction."""
    async with sessionmaker() as session, session.begin():
        # A missing tenant row cannot be protected by SELECT FOR UPDATE. Serialize production applies
        # per tenant with a transaction-scoped advisory lock so concurrent first runs cannot race.
        if apply and session.bind is not None and session.bind.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:tenant))"),
                {"tenant": manifest.tenant.slug},
            )
        tenant_row = await session.get(TenantRow, manifest.tenant.slug, with_for_update=apply)

        emails = [user.email for user in manifest.users]
        user_query = select(UserRow).where(func.lower(UserRow.email).in_(emails))
        if apply:
            user_query = user_query.with_for_update()
        existing_users = (await session.execute(user_query)).scalars().all() if emails else []
        users_by_email = {row.email.lower(): row for row in existing_users}
        if len(users_by_email) != len(existing_users):
            raise ProvisioningError("multiple existing users match a manifest email")

        agent_ids = [agent.id for agent in manifest.agents]
        agent_query = select(AgentRow).where(AgentRow.id.in_(agent_ids))
        if apply:
            agent_query = agent_query.with_for_update()
        existing_agents = (await session.execute(agent_query)).scalars().all() if agent_ids else []
        agents_by_id = {row.id: row for row in existing_agents}

        for row in existing_users:
            if row.tenant_id != manifest.tenant.slug:
                raise ProvisioningError("a manifest user email belongs to another tenant")
        for row in existing_agents:
            if row.tenant_id != manifest.tenant.slug:
                raise ProvisioningError("a manifest agent id belongs to another tenant")

        user_changes: list[_UserChange] = []
        for desired in manifest.users:
            row = users_by_email.get(desired.email)
            if row is None:
                user_changes.append(_UserChange(
                    desired=desired,
                    row=None,
                    # Generate a unique, unrecoverable bootstrap credential. The user establishes
                    # their own password through the email reset flow; no shared password exists.
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                    role_changed=False,
                ))
                continue
            password_hash = None
            if reset_existing_passwords:
                password_hash = hash_password(secrets.token_urlsafe(32))
            user_changes.append(_UserChange(
                desired=desired,
                row=row,
                password_hash=password_hash,
                role_changed=row.role != desired.role,
            ))

        agent_changes: list[_AgentChange] = []
        for desired in manifest.agents:
            row = agents_by_id.get(desired.id)
            merged_config = {**(row.config or {}), **desired.config} if row is not None else dict(desired.config)
            changed = row is None or (
                row.name != desired.name
                or row.atype != desired.atype
                or row.status != desired.status
                or (row.config or {}) != merged_config
            )
            agent_changes.append(_AgentChange(
                desired=desired,
                row=row,
                merged_config=merged_config,
                changed=changed,
            ))

        result = ProvisioningResult(
            tenant=manifest.tenant.slug,
            tenants_created=int(tenant_row is None),
            tenants_updated=int(tenant_row is not None and tenant_row.name != manifest.tenant.display_name),
            users_created=sum(change.row is None for change in user_changes),
            users_updated=sum(
                change.row is not None and (change.role_changed or change.password_hash is not None)
                for change in user_changes
            ),
            passwords_reset=sum(
                change.row is not None and change.password_hash is not None for change in user_changes
            ),
            agents_created=sum(change.row is None for change in agent_changes),
            agents_updated=sum(change.row is not None and change.changed for change in agent_changes),
        )
        if not apply:
            return result

        if tenant_row is None:
            session.add(TenantRow(id=manifest.tenant.slug, name=manifest.tenant.display_name))
        elif tenant_row.name != manifest.tenant.display_name:
            tenant_row.name = manifest.tenant.display_name

        for change in user_changes:
            if change.row is None:
                session.add(UserRow(
                    id=uuid.uuid4().hex[:12],
                    email=change.desired.email,
                    password_hash=change.password_hash,
                    tenant_id=manifest.tenant.slug,
                    role=change.desired.role,
                ))
            else:
                if change.role_changed:
                    change.row.role = change.desired.role
                if change.password_hash is not None:
                    change.row.password_hash = change.password_hash

        for change in agent_changes:
            if change.row is None:
                session.add(AgentRow(
                    id=change.desired.id,
                    tenant_id=manifest.tenant.slug,
                    name=change.desired.name,
                    atype=change.desired.atype,
                    status=change.desired.status,
                    config=change.merged_config,
                ))
            elif change.changed:
                change.row.name = change.desired.name
                change.row.atype = change.desired.atype
                change.row.status = change.desired.status
                change.row.config = change.merged_config

        await session.flush()
        return result
