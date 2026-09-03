"""Shared pagination for the admin directories.

Extracted because the same body was duplicated in CustomerDirectory.list and
SqlCustomerDirectory.list, and because both carried the same latent defect: `page` was unvalidated,
so page=0 computed a start offset of -20 and returned an empty list alongside a non-zero total, and
page=-1 returned the LAST rows of the directory while reporting page -1. An operator paging through a
customer list would have seen either nothing or the wrong end of the list with no error.
"""
from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from pydantic import BaseModel

PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

T = TypeVar("T")
_ItemT = TypeVar("_ItemT")


class PaginatedOut(BaseModel, Generic[_ItemT]):
    """The {total, page, page_size, items} envelope repeated across the admin and billing list
    routes. Concretize per route: response_model=PaginatedOut[CustomerDirectoryRow]."""

    total: int
    page: int
    page_size: int
    items: list[_ItemT]


def paginate(rows: Sequence[T], *, page: int = 1, page_size: int = PAGE_SIZE) -> dict:
    """One page of rows plus the unpaginated total.

    Clamps rather than raises: these are read-only directory listings reached from a URL an operator
    may have edited, and a clamped first page is a better answer than a 500 or a silently wrong slice.
    """
    size = int(page_size) if page_size else PAGE_SIZE
    if size < 1:
        # A negative size is exactly as unspecified as zero, so it falls back rather than to one row.
        size = PAGE_SIZE
    size = min(size, MAX_PAGE_SIZE)

    requested = int(page) if page else 1
    last = max(1, -(-len(rows) // size))  # ceil division
    # Clamped at BOTH ends. Clamping only the low end would leave the exact defect this module exists
    # to fix reachable from the other direction: page=999 returning an empty list next to a non-zero
    # total, which reads as "no results".
    current = min(max(1, requested), last)
    start = (current - 1) * size
    return {"total": len(rows), "page": current, "items": list(rows[start:start + size])}
