"""First-party ingestion source catalog (ported from Staging IdgSalesSourceCatalog).

TED and UNGM are the live first-party portals (each with its own scannable connector). Custom
sources are attached per-agent with the `generic` connector and do not appear in this catalog;
they show up in the agent's source list instead. The catalog is the pick-list of first-party
portals a user can add to an agent.
"""
from __future__ import annotations

_DEFAULT_INGEST_FILTERS = {
    "query_enabled": True,
    "query_keyword": "security",
    "all_countries": True,
    "all_categories": True,
}

# Ordered first-party definitions. Keep TED first then UNGM to match the deployed source ordering.
DEFINITIONS: list[dict] = [
    {
        "key": "ted",
        "name": "TED - EU Tenders",
        "description": "EU Tenders Electronic Daily (TED) public API",
        "type": "portal",
        "auth_status": "public_api",
        "scannable": True,
        "connector": "ted",
        "config": {
            "url": "https://ted.europa.eu/en/",
            "api_url": "https://api.ted.europa.eu/v3/notices/search",
            "ingest_filters": _DEFAULT_INGEST_FILTERS,
        },
    },
    {
        "key": "ungm",
        "name": "UNGM Public Notices",
        "description": "UN Global Marketplace public notices",
        "type": "portal",
        "auth_status": "public_details_limited",
        "scannable": True,
        "connector": "ungm",
        "config": {
            "url": "https://www.ungm.org/Public/Notice",
            "default_query": "",
            "ingest_filters": _DEFAULT_INGEST_FILTERS,
        },
    },
]

# Connector ids that can actually fetch notices. `generic` is added with the generic HTTP connector.
CONNECTOR_KEYS = ("ungm", "ted", "generic")


def keys() -> list[str]:
    return [d["key"] for d in DEFINITIONS]


def definition(source_key: str) -> dict | None:
    key = (source_key or "").strip().lower()
    return next((d for d in DEFINITIONS if d["key"] == key), None)


def is_valid_key(source_key: str) -> bool:
    return definition(source_key) is not None


def display_name(source_key: str) -> str:
    d = definition(source_key)
    return d["name"] if d else (source_key or "").strip().upper()


def is_scannable(source_key: str) -> bool:
    d = definition(source_key)
    return bool(d["scannable"]) if d else False


def connector_key(source_key: str) -> str:
    """The connector a source uses: a first-party definition's connector, else `generic` for
    custom (catalog-unknown) keys."""
    d = definition(source_key)
    return d["connector"] if d else "generic"


def is_valid_connector(connector: str) -> bool:
    return (connector or "").strip().lower() in CONNECTOR_KEYS


def catalog_item_out(defn: dict, *, already_added: bool) -> dict:
    """Serialize a catalog definition to the camelCase shape the FE consumes (mirrors Staging
    IdgSalesSourceCatalogResource)."""
    config = defn.get("config", {}) or {}
    return {
        "key": defn.get("key"),
        "name": defn.get("name"),
        "description": defn.get("description"),
        "type": defn.get("type", "portal"),
        "authStatus": defn.get("auth_status"),
        "scannable": bool(defn.get("scannable", False)),
        "alreadyAdded": already_added,
        "defaultConfig": {
            "url": config.get("url"),
            "apiUrl": config.get("api_url"),
            "defaultQuery": config.get("default_query", ""),
            "ingestFilters": config.get("ingest_filters"),
        },
    }
