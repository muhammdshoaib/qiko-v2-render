"""Environment list and tenant-scoped spec projection (JM2-1134).

These are pure-function tests: no app, no client, no database. The route-level behaviour
lives in test_api_docs_routes.py.
"""
import json
from pathlib import Path
from typing import Iterator

from app.modules.api_docs.environments import ENVIRONMENTS, enabled_servers
from app.modules.api_docs.spec_filter import TENANT_SPECS, filter_spec

PREPROD_SERVER = {"url": "https://preprod.qiko.ai/api/v1", "description": "Preprod"}

FULL_SPEC = json.loads((Path(__file__).resolve().parents[1] / "openapi.json").read_text())


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


def test_only_enabled_environments_are_served():
    assert enabled_servers() == [PREPROD_SERVER]


def test_live_is_defined_but_disabled():
    """Live must stay off until the production promotion: the routes do not exist on
    qiko.ai before it, so offering the server would serve 404s to every caller."""
    live = next(e for e in ENVIRONMENTS if e.name == "Live")
    assert live.url == "https://qiko.ai/api/v1"
    assert live.enabled is False


def test_unmapped_tenant_yields_none():
    assert filter_spec(FULL_SPEC, "not-a-tenant") is None


def test_mapping_is_explicit_not_derived():
    """A derived tag would publish any future tenant whose routes happen to match, without
    anyone deciding to publish it."""
    assert set(TENANT_SPECS) == {"joseph-mews"}
    assert TENANT_SPECS["joseph-mews"].tag == "joseph-mews-worker"


def test_filtered_document_holds_only_that_tenants_operations():
    document = filter_spec(FULL_SPEC, "joseph-mews")
    assert document is not None
    assert document["paths"], "expected the joseph-mews worker paths"
    for operations in document["paths"].values():
        for operation in operations.values():
            assert "joseph-mews-worker" in operation["tags"]


def test_no_foreign_paths_leak():
    document = filter_spec(FULL_SPEC, "joseph-mews")
    assert not [p for p in document["paths"] if "/tenants/{tenant_id}" not in p]
    assert not [p for p in document["paths"] if "/admin" in p or "/billing" in p]


def test_every_ref_resolves_inside_the_document():
    """A subset that references a schema it does not carry is not importable, which is the
    whole point of extracting it."""
    document = filter_spec(FULL_SPEC, "joseph-mews")
    schemas = document["components"]["schemas"]
    for ref in _refs(document):
        assert ref.startswith("#/components/schemas/"), ref
        assert ref.split("/")[-1] in schemas, ref


def test_servers_come_from_the_enabled_environments():
    document = filter_spec(FULL_SPEC, "joseph-mews")
    assert document["servers"] == [PREPROD_SERVER]


def test_info_matches_the_docs_repo_generator():
    """Parity with joseph-mews-api-docs/refresh_qiko_core_spec.py. A drift job compares the
    two documents, so these strings are a contract, not cosmetics."""
    document = filter_spec(FULL_SPEC, "joseph-mews")
    assert document["info"]["title"] == "Joseph Mews Worker API"
    assert document["info"]["description"] == (
        "Service-to-service AI generation endpoints for the Joseph Mews worker "
        "(Intent Signal summaries, Portfolio Insights)."
    )
    assert document["info"]["version"] == FULL_SPEC["info"]["version"]
    assert document["openapi"] == FULL_SPEC["openapi"]


def test_document_has_no_keys_beyond_the_agreed_shape():
    document = filter_spec(FULL_SPEC, "joseph-mews")
    assert set(document) == {"openapi", "info", "servers", "paths", "components"}
    assert set(document["components"]) == {"schemas"}
