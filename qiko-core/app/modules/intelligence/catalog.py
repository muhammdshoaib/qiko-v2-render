"""The source catalog and the connector contract.

This is the seam that makes the vertical open. Adding a source is writing one connector and
registering one entry; nothing in the worker, the digest, the chat or the UI changes. If a change
to any of those is ever needed to add a source, this abstraction has failed and is worth fixing
rather than working around.

Follows `app.modules.sales_intelligence.source_catalog`, which already does this for tender
portals, with one addition: a source may register with **no connector**. Uploaded documents and
research runs produce signals directly and nothing polls them, but they are still sources, and
they still appear in the UI and in retrieval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.modules.intelligence.models import Signal, SignalStore


class UnknownSource(Exception):
    """Asked for a source that was never registered. Never guessed at."""


@runtime_checkable
class Connector(Protocol):
    """Reads a third-party system and emits normalised signals.

    Every implementation is READ-ONLY. This worker observes; the single write path in the product
    is the human-approved backlog proposal, and it does not go through a connector.
    """

    key: str

    async def fetch_since(self, *, config: dict, credential: str,
                          since: datetime, tenant: str, agent_id: str,
                          signal_store: "SignalStore" | None = None) -> list[Signal]:
        """Signals from this source since `since`. Must be idempotent: callers re-read an
        overlapping window on every sweep and rely on `external_id` to deduplicate.

        `signal_store` is provided so poll-and-diff strategies can compare against previously
        ingested state without introducing a second persistence seam. `tenant` and `agent_id`
        scope every emitted Signal.
        """
        ...

    async def verify(self, *, config: dict, credential: str) -> dict:
        """Check the credential and report what it can see. Backs the Test button.

        Must never mutate anything at the third party. A test that changes state is not a test.
        """
        ...


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    name: str
    description: str = ""
    connector: Connector | None = None

    @property
    def pollable(self) -> bool:
        """Whether a scheduled sweep should fetch from it. False for sources that push or that
        are produced in-product, which must not appear in the poller's work list."""
        return self.connector is not None


@dataclass
class SourceCatalog:
    """The registry of sources a worker can attach."""

    _definitions: dict[str, SourceDefinition] = field(default_factory=dict)

    def register(self, *, key: str, name: str, connector: Connector | None,
                 description: str = "") -> SourceDefinition:
        # A duplicate key would make dispatch depend on import order, which is the kind of bug
        # that only shows up once two people have added a source in the same release.
        if key in self._definitions:
            raise ValueError(f"source {key!r} is already registered")
        definition = SourceDefinition(key=key, name=name, description=description,
                                      connector=connector)
        self._definitions[key] = definition
        return definition

    def definition(self, key: str) -> SourceDefinition | None:
        return self._definitions.get(key)

    def keys(self) -> list[str]:
        return list(self._definitions)

    def pollable_keys(self) -> list[str]:
        return [k for k, d in self._definitions.items() if d.pollable]

    def connector_for(self, key: str) -> Connector:
        definition = self._definitions.get(key)
        if definition is None or definition.connector is None:
            raise UnknownSource(key)
        return definition.connector

    def items(self, *, connected: set[str] | None = None,
              configured: set[str] | None = None) -> list[dict]:
        """Serialise for the frontend. `connected` is the set of keys this worker has configured,
        and `configured` is the set of keys the tenant has globally set up, so one call renders
        what is available, ready, and already attached."""
        attached = connected or set()
        ready = configured or set(self._definitions.keys())
        return [{"key": d.key, "name": d.name, "description": d.description,
                 "pollable": d.pollable, "connected": d.key in attached,
                 "configured": d.key in ready}
                for d in self._definitions.values()]
