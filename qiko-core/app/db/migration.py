"""Idempotent, re-runnable data migration from the legacy Laravel/SQLite databases into unified
Postgres. Every row is upserted by primary key, so re-running never duplicates and safely picks up
changed rows; a dry-run reports what would change without writing. The legacy readers (connecting to
the old MySQL/SQLite/Pinecone) are integration; this module owns the idempotent load + parity.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Agent as AgentRow
from app.db.models import Conversation as ConversationRow
from app.db.models import Message as MessageRow
from app.db.models import User as UserRow


@dataclass
class MigrationReport:
    inserted: int = 0
    updated: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated


async def upsert_rows(sm: async_sessionmaker[AsyncSession], model, rows: list[dict], *,
                      key: str = "id", transform: Callable[[dict], dict] | None = None,
                      dry_run: bool = False) -> MigrationReport:
    """Generic idempotent upsert by primary key for any mapped model."""
    report = MigrationReport()
    async with sm() as s:
        for raw in rows:
            r = transform(raw) if transform else dict(raw)
            existing = await s.get(model, r[key])
            if existing is None:
                report.inserted += 1
                if not dry_run:
                    s.add(model(**r))
            else:
                report.updated += 1
                if not dry_run:
                    for k, v in r.items():
                        if k != key:
                            setattr(existing, k, v)
        if not dry_run:
            await s.commit()
    return report


async def count_rows(sm: async_sessionmaker[AsyncSession], model) -> int:
    async with sm() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


def reconcile_user(raw: dict) -> dict:
    """Reconcile the two legacy user shapes into the unified row.

    qiko-backend replaced email/password with `user_name`/`passfield`; qiko-admin-backend keeps
    `email`/`password`. We accept either so both sources migrate into one users table.
    """
    email = (raw.get("email") or raw.get("user_name") or "").lower()
    return {
        "id": raw["id"],
        "email": email,
        "password_hash": raw.get("password_hash") or raw.get("passfield") or raw.get("password") or "",
        "tenant_id": raw.get("tenant_id"),
        "role": raw.get("role", "viewer"),
    }


# --- backward-compatible user helpers ---
async def upsert_users(sm, rows: list[dict], *, dry_run: bool = False) -> MigrationReport:
    return await upsert_rows(sm, UserRow, rows, transform=reconcile_user, dry_run=dry_run)


async def parity_count(sm) -> int:
    return await count_rows(sm, UserRow)


# --- per-table convenience wrappers (idempotent) ---
async def upsert_agents(sm, rows, *, dry_run=False) -> MigrationReport:
    return await upsert_rows(sm, AgentRow, rows, dry_run=dry_run)


async def upsert_conversations(sm, rows, *, dry_run=False) -> MigrationReport:
    return await upsert_rows(sm, ConversationRow, rows, dry_run=dry_run)


async def upsert_messages(sm, rows, *, dry_run=False) -> MigrationReport:
    return await upsert_rows(sm, MessageRow, rows, dry_run=dry_run)
