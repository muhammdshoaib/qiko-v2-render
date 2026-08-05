"""Shared pagination for the admin directories.

Extracted because the same body was duplicated in CustomerDirectory.list and
SqlCustomerDirectory.list, and because both carried the same latent defect: `page` was unvalidated,
so page=0 computed a start offset of -20 and returned an empty list alongside a non-zero total, and
page=-1 returned the LAST rows of the directory while reporting page -1. An operator paging through a
customer list would have seen either nothing or the wrong end of the list with no error.
"""
from __future__ import annotations

from typing import Sequence, TypeVar

PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

T = TypeVar("T")


def paginate(rows: Sequence[T], *, page: int = 1, page_size: int = PAGE_SIZE) -> dict:
    """One page of rows plus the unpaginated total.

    Clamps rather than raises: these are read-only directory listings reached from a URL an operator
    may have edited, and a clamped first page is a better answer than a 500 or a silently wrong slice.
    """
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or PAGE_SIZE), MAX_PAGE_SIZE))
    start = (page - 1) * page_size
    return {"total": len(rows), "page": page, "items": list(rows[start:start + page_size])}
