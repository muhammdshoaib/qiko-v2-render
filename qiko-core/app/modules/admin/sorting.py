"""Shared, allowlisted sorting for the admin directories.

Why an allowlist and not a field name
-------------------------------------
The sort key arrives from a query string. Passing it to `getattr` or interpolating it into SQL would
let a caller read or order by any attribute of the row, including ones the endpoint deliberately does
not return (a password hash sorts differently for every value, which leaks information about it). So
each endpoint declares exactly which columns it will sort by, and anything else is a 422 rather than a
silent fallback: a filter that quietly ignores what you asked for is worse than one that refuses.

Sorting happens in Python because these endpoints already materialise the full filtered list before
paginating. That is a pre-existing property, not one this module introduces, and it is why adding sort
here is cheap. When a directory outgrows it, the allowlist maps one-to-one onto ORDER BY columns.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

from fastapi import HTTPException

Order = Literal["asc", "desc"]

# Per-endpoint sortable fields, mapping the public sort name to a key function. Public names are part
# of the API contract, so they are chosen to match the field names in the response rather than the
# column names in the database.
SortSpec = dict[str, Callable[[Any], Any]]


def _text(value: Any) -> str:
    """Case-insensitive, None-safe text key so a missing name does not crash the sort."""
    return str(value or "").lower()


# /admin/customers returns user_id, email, plan and earnings only.
CUSTOMER_SORTS: SortSpec = {
    "email": lambda row: _text(row.email),
    "plan": lambda row: _text(row.plan),
    "earnings": lambda row: row.earnings_cents,
}

# /admin/tenants returns the same rows plus the two counts, so it can sort by them. Kept as a separate
# spec rather than one shared map, because sorting by a field the response does not contain lets a
# caller infer that field's ordering without ever being shown it.
TENANT_SORTS: SortSpec = {
    **CUSTOMER_SORTS,
    "users": lambda row: getattr(row, "users", 0),
    "workers": lambda row: getattr(row, "agents", 0),
}

USER_SORTS: SortSpec = {
    "email": lambda row: _text(row["email"]),
    "name": lambda row: _text(row["name"]),
    "tenant": lambda row: _text(row["tenant_id"]),
    "role": lambda row: _text(row["role"]),
    # Sorting by "who has 2FA off" is how an operator finds the accounts to chase.
    "twofa": lambda row: bool(row["twofa_enabled"]),
}

WORKER_SORTS: SortSpec = {
    "name": lambda row: _text(row["name"]),
    "tenant": lambda row: _text(row["tenant_id"]),
    "status": lambda row: _text(row["status"]),
    "enabled": lambda row: bool(row["enabled"]),
    "created": lambda row: str(row["created_at"] or ""),
}

MONITORING_SORTS: SortSpec = {
    "name": lambda row: _text(row["name"]),
    "tenant": lambda row: _text(row["tenant_id"]),
    "calls": lambda row: row["calls"],
    "status": lambda row: _text(row["status"]),
    "enabled": lambda row: bool(row["enabled"]),
    # last_seen is None for a worker with no activity in the window. None sorts before any timestamp,
    # so descending puts the most recently active first and the never-used last, which is the useful
    # order rather than a crash.
    "last_seen": lambda row: str(row["last_seen"] or ""),
}


def apply_sort(rows: Sequence[Any], spec: SortSpec, sort: str | None, order: str) -> list[Any]:
    """Sort by an allowlisted field, or refuse.

    Returns the rows unchanged when no sort is requested, so each endpoint keeps its existing default
    order (busiest first, highest earning first) rather than silently switching to alphabetical.
    """
    rows = list(rows)
    if not sort:
        return rows
    key = spec.get(sort)
    if key is None:
        raise HTTPException(
            status_code=422,
            detail=f"cannot sort by '{sort}'. Sortable fields: {', '.join(sorted(spec))}")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="order must be 'asc' or 'desc'")
    return sorted(rows, key=key, reverse=order == "desc")
