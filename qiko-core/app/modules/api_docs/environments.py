"""Environments the documented contract can be exercised against (JM2-1134).

Live is defined but disabled. These routes reach preprod when main is promoted to preprod,
and only reach qiko.ai after a separate production promotion, so publishing the live server
before that would hand every caller a 404 from a page that claims to document a working API.

Turning live on is one flag here. test_api_docs_filter asserts the emitted list, so it
cannot happen as a side effect of an unrelated change.
"""
from __future__ import annotations

from typing import NamedTuple


class Environment(NamedTuple):
    url: str
    name: str
    enabled: bool


ENVIRONMENTS: tuple[Environment, ...] = (
    Environment(url="https://preprod.qiko.ai/api/v1", name="Preprod", enabled=True),
    Environment(url="https://qiko.ai/api/v1", name="Live", enabled=False),
)


def enabled_servers() -> list[dict[str, str]]:
    """The OpenAPI `servers` block. Must stay identical to the list emitted by the docs
    repository's refresh_qiko_core_spec.py, because a drift job compares the two documents
    and would otherwise fail on this block alone."""
    return [{"url": e.url, "description": e.name} for e in ENVIRONMENTS if e.enabled]
