"""Data-migration runner: read a legacy SQLite DB and upsert into the unified Postgres target.

Usage: python -m app.db.migrate_cli <legacy.sqlite> [--dry-run]
The upserts are idempotent (safe to re-run); --dry-run reports without writing.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import migration
from app.db.legacy_readers import read_sqlite_table


async def run_sqlite_migration(legacy_path: str, sm: async_sessionmaker[AsyncSession], *,
                               dry_run: bool = False) -> dict:
    """Migrate the known tables from a legacy SQLite DB. Returns a per-table {inserted, updated}."""
    report: dict[str, dict] = {}
    plan = [
        ("users", migration.upsert_users),
        ("agents", migration.upsert_agents),
        ("conversations", migration.upsert_conversations),
        ("messages", migration.upsert_messages),
    ]
    for table, upsert in plan:
        rows = read_sqlite_table(legacy_path, table)
        if not rows:
            continue
        rep = await upsert(sm, rows, dry_run=dry_run)
        report[table] = {"inserted": rep.inserted, "updated": rep.updated}
    return report


def main() -> None:  # pragma: no cover - CLI entrypoint (needs a live target DB)
    import asyncio
    import sys

    from app.core.db import build_engine, build_sessionmaker

    args = sys.argv[1:]
    dry = "--dry-run" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        raise SystemExit("usage: python -m app.db.migrate_cli <legacy.sqlite> [--dry-run]")
    sm = build_sessionmaker(build_engine())
    report = asyncio.run(run_sqlite_migration(paths[0], sm, dry_run=dry))
    print(report)


if __name__ == "__main__":  # pragma: no cover
    main()
