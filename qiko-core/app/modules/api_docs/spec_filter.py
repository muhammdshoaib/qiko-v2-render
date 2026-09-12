"""Tenant-scoped projection of the live OpenAPI document (JM2-1134).

qiko-core serves 269 paths across many customers. A customer integrating one worker should
receive only that worker's contract, as a document that resolves on its own.

The tenant to tag mapping is explicit rather than derived from the tenant id. Deriving it
(f"{tenant_id}-worker") would publish any future tenant whose routes happen to carry a
matching tag, without anyone deciding to publish it. An unmapped tenant yields None, which
the router turns into a 404.

Output parity matters: joseph-mews-api-docs holds a committed copy produced by its own
refresh_qiko_core_spec.py, and a drift job compares the two after key-order normalisation.
The info strings below are copied from that script deliberately, not written afresh.
"""
from __future__ import annotations

from typing import Iterator, NamedTuple

from app.modules.api_docs.environments import enabled_servers


class TenantSpec(NamedTuple):
    tag: str
    title: str
    description: str


TENANT_SPECS: dict[str, TenantSpec] = {
    "joseph-mews": TenantSpec(
        tag="joseph-mews-worker",
        title="Joseph Mews Worker API",
        description=(
            "Service-to-service AI generation endpoints for the Joseph Mews worker "
            "(Intent Signal summaries, Portfolio Insights)."
        ),
    ),
}


def _refs(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            yield ref
        for value in node.values():
            yield from _refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value)


def filter_spec(full: dict, tenant_id: str) -> dict | None:
    spec = TENANT_SPECS.get(tenant_id)
    if spec is None:
        return None

    paths: dict[str, dict] = {}
    for path, operations in full["paths"].items():
        matching = {
            method: operation
            for method, operation in operations.items()
            if spec.tag in (operation.get("tags") or [])
        }
        if matching:
            paths[path] = matching

    available = full.get("components", {}).get("schemas", {})
    needed: dict[str, object] = {}
    frontier = set(_refs(paths))
    while frontier:
        name = frontier.pop().split("/")[-1]
        if name in needed or name not in available:
            continue
        needed[name] = available[name]
        frontier |= set(_refs(available[name]))

    return {
        "openapi": full["openapi"],
        "info": {
            "title": spec.title,
            "version": full["info"]["version"],
            "description": spec.description,
        },
        "servers": enabled_servers(),
        "paths": paths,
        "components": {"schemas": needed},
    }
