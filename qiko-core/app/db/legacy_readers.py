"""Readers for the legacy databases, feeding the idempotent upserts in db/migration.py.

SQLite is fully supported with the stdlib (used by qiko-mcp-wrapper). MySQL/Postgres (the Laravel
backends) use the same row-dict shape via SQLAlchemy; the connection there needs credentials, so it
is wired at cutover. Keeping the readers here (separate from the upserts) keeps the load testable.
"""
from __future__ import annotations

import re
import sqlite3

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_table(table: str) -> str:
    if not _IDENT.match(table):
        raise ValueError(f"unsafe table name: {table}")
    return table


def read_sqlite_table(db_path: str, table: str) -> list[dict]:
    """Read all rows of a table from a legacy SQLite database as dicts. Returns [] if it is absent."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            return []
        return [dict(r) for r in conn.execute(f"SELECT * FROM {_safe_table(table)}").fetchall()]
    finally:
        conn.close()
