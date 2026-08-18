"""Ingestion helpers for Intelligence Worker sources.

A connector returns normalised `Signal`s; these helpers add them to the `SignalStore` and index a
human-readable rendering into the worker's knowledge corpus. Deduplication lives in `SignalStore.add`;
callers can re-read the same window and only new signals are written or indexed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.modules.intelligence.catalog import SourceCatalog
from app.modules.intelligence.models import Signal, SignalStore
from app.modules.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)


async def ingest_source(tenant: str, agent_id: str, source: str, config: dict, credential: str,
                        *, catalog: SourceCatalog, signal_store: SignalStore,
                        knowledge: KnowledgeService | None = None,
                        since: datetime | None = None) -> dict:
    """Fetch signals from `source` and write any new ones to storage/knowledge.

    Returns a summary with `added`, `existing` and `errors` counts so the caller can report it.
    """
    connector = catalog.connector_for(source)
    if since is None:
        since = datetime.min.replace(tzinfo=timezone.utc)
    signals = await connector.fetch_since(
        config=config, credential=credential, since=since,
        tenant=tenant, agent_id=agent_id, signal_store=signal_store)

    added = 0
    existing = 0
    errors = 0
    for signal in signals:
        try:
            is_new = await signal_store.add(signal)
        except Exception as exc:  # noqa: BLE001 - a single signal must not abort the batch
            logger.warning("failed to ingest signal %s: %s", signal.external_id, exc)
            errors += 1
            continue
        if is_new:
            added += 1
            if knowledge is not None:
                try:
                    await knowledge.ingest(
                        signal.tenant, _signal_doc_id(signal), _signal_text(signal),
                        agent_id=signal.agent_id)
                except Exception as exc:  # noqa: BLE001 - indexing failure must not drop the signal
                    logger.warning("failed to index signal %s: %s", signal.external_id, exc)
                    errors += 1
        else:
            existing += 1
    return {"added": added, "existing": existing, "errors": errors}


def _signal_doc_id(signal: Signal) -> str:
    """Stable document id for a signal in the knowledge corpus."""
    return f"{signal.source}:{signal.external_id}"


def _signal_text(signal: Signal) -> str:
    """Human-readable text used for retrieval and citations."""
    parts = [signal.title, signal.body]
    if signal.actor:
        parts.append(f"by {signal.actor}")
    if signal.occurred_at:
        parts.append(f"at {signal.occurred_at.isoformat()}")
    if signal.ref:
        parts.append(f"({signal.ref})")
    return "\n".join(p for p in parts if p)
