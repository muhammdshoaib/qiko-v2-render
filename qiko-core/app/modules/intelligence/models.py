"""The normalised event every source emits, and the store protocol over it.

`Signal` is the single shape that makes this vertical open to new sources. A connector, an
uploaded document and a research run all produce it, so the chat, the digest, the correlation
layer and the UI each have exactly one thing to understand. Adding a source must never require a
second code path in any of them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

# The tail of a conversation is what any consumer actually needs. Capping the read bounds the
# prompt built from it and the memory held while building it (LLM10 / API4).
DEFAULT_SIGNAL_LIMIT = 200


@dataclass
class Signal:
    """One thing that happened, from any source.

    Two fields are easy to confuse and answer different questions:

    `container` is WHERE it happened. A source-defined grouping key: for Slack the workspace and
    channel, for GitHub the repository, for Qiko Track the project. The digest groups by it. It
    carries the workspace, not just the channel, because a channel id is unique only *within* a
    workspace and two workspaces sharing one must never merge into a single conversation.

    `ref` is WHICH WORK ITEM it concerns. A ticket key, a PR number: the join key that lets a
    Slack claim be compared against a Qiko Track state and a GitHub merge. Most signals have no
    `ref`, and one without it can only ever be reported as context, never as evidence.

    `meta` holds source-specific fields that only that source's own code reads (a Slack thread
    timestamp, an enterprise id). Keeping them out of the core shape is what stops `Signal` from
    slowly becoming the union of every source's schema.
    """

    tenant: str
    agent_id: str
    source: str
    kind: str
    external_id: str
    container: str
    actor: str
    title: str
    body: str
    occurred_at: datetime
    ref: str | None = None
    url: str | None = None
    tags: list[str] = field(default_factory=list)
    flagged: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def dedupe_key(self) -> tuple[str, str, str, str]:
        """Identity for ingestion. Scoped per worker and source, so two sources may legitimately
        use the same id and two workers watching one workspace each keep their own copy."""
        return (self.tenant, self.agent_id, self.source, self.external_id)


class SignalStore(Protocol):
    """Tenant- and agent-scoped signal storage.

    `add` returns whether the signal was new, so a caller can tell an ingest from a re-read
    without a second query. Every connector re-reads an overlapping window, so this is the
    common case rather than an edge case.
    """

    async def add(self, signal: Signal) -> bool: ...

    async def list_recent(self, tenant: str, agent_id: str, *, source: str | None = None,
                          container: str | None = None, since: datetime | None = None,
                          limit: int = DEFAULT_SIGNAL_LIMIT) -> list[Signal]: ...

    async def clear(self, tenant: str, agent_id: str, *, source: str | None = None,
                    container: str | None = None) -> int: ...

    async def purge_older_than(self, older_than: timedelta,
                                source: str | None = None) -> int: ...

    async def list_older_than(self, older_than: timedelta,
                              source: str | None = None) -> list[Signal]: ...


@dataclass
class InMemorySignalStore:
    """Dev and test store. Not multi-process safe, wiped on restart.

    Selection semantics here are the contract the SQL store must match exactly. Where the two
    disagree, the tests are testing something that is not what ships.
    """

    _signals: list[Signal] = field(default_factory=list)

    async def add(self, signal: Signal) -> bool:
        if any(s.dedupe_key == signal.dedupe_key for s in self._signals):
            return False
        self._signals.append(signal)
        return True

    async def list_recent(self, tenant: str, agent_id: str, *, source: str | None = None,
                          container: str | None = None, since: datetime | None = None,
                          limit: int = DEFAULT_SIGNAL_LIMIT) -> list[Signal]:
        matching = [s for s in self._signals
                    if self._matches(s, tenant, agent_id, source, container)
                    and (since is None or s.occurred_at >= since)]
        matching.sort(key=lambda s: s.occurred_at)
        # Newest `limit`, returned oldest-first so a transcript built from them reads in order.
        return matching[-limit:]

    async def clear(self, tenant: str, agent_id: str, *, source: str | None = None,
                    container: str | None = None) -> int:
        before = len(self._signals)
        self._signals = [s for s in self._signals
                         if not self._matches(s, tenant, agent_id, source, container)]
        return before - len(self._signals)

    async def purge_older_than(self, older_than: timedelta,
                               source: str | None = None) -> int:
        old = await self.list_older_than(older_than, source=source)
        old_keys = {s.dedupe_key for s in old}
        self._signals = [s for s in self._signals if s.dedupe_key not in old_keys]
        return len(old)

    async def list_older_than(self, older_than: timedelta,
                              source: str | None = None) -> list[Signal]:
        cutoff = datetime.now(timezone.utc) - older_than
        return [
            s for s in self._signals
            if s.occurred_at < cutoff and (source is None or s.source == source)]

    @staticmethod
    def _matches(signal: Signal, tenant: str, agent_id: str,
                 source: str | None, container: str | None) -> bool:
        # tenant and agent_id are never optional: there is no read across workers, by construction.
        return (signal.tenant == tenant and signal.agent_id == agent_id
                and (source is None or signal.source == source)
                and (container is None or signal.container == container))
