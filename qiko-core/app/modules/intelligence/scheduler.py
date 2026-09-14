"""Background scheduler sweep for the Intelligence Worker (QIW-1023).

GitHub and Qiko Track signals were only ever ingested once, at the moment a source was first
connected (see intelligence/router.py's connect_source). GitHub alone got a reactive top-up
during chat (_ensure_github_signals_for_chat), gated on a keyword match and a 30-day cooldown;
Qiko Track had no refresh path at all. This sweep makes both sources refresh on a fixed interval
regardless of whether anyone happens to ask a matching chat question, mirroring the shape of
app.modules.sales_intelligence.scheduler.scan_due_sources.

Slack is deliberately excluded: it is push-based (Events API webhook), not pollable, and does
not appear in SourceCatalog.pollable_keys().
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.modules.intelligence.catalog import SourceCatalog
from app.modules.intelligence.ingest import ingest_source
from app.modules.intelligence.models import SignalStore
from app.modules.intelligence.router import _github_credential, _qiko_track_credential

logger = logging.getLogger(__name__)

# Fixed sweep interval. No per-source cadence config exists for this vertical (unlike
# sales_intelligence's IngestionSource.scan_cadence) - a single fixed interval is the smallest
# safe change; a per-source cadence can be added later if one interval proves wrong for everyone.
DEFAULT_INTERVAL_MINUTES = 60


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def _is_signal_source_due(signal_store: SignalStore, tenant: str, agent_id: str, *,
                                source: str, interval_minutes: int,
                                now: datetime) -> tuple[bool, datetime]:
    """Return `(is_due, since)`.

    Due when there is no signal yet from this source, or the freshest one is at least one
    sweep interval old. `list_recent` with `limit=1` returns at most one row, so there is no
    ordering ambiguity: that one row is the freshest signal by construction.

    `since` is the bound a caller should pass to `ingest_source` for this fetch: the freshest
    existing signal's `occurred_at` (an incremental fetch), or - when no signal exists yet -
    `now - interval_minutes` as a floor. A source connected but with zero signals should only
    happen momentarily at connect time (which already runs its own unbounded initial ingest);
    the sweep itself must never fetch unbounded history."""
    recent = await signal_store.list_recent(tenant, agent_id, source=source, limit=1)
    if not recent:
        return True, now - timedelta(minutes=max(1, interval_minutes))
    freshest = _as_utc(recent[0].occurred_at)
    due = freshest + timedelta(minutes=max(1, interval_minutes)) <= now
    return due, freshest


async def sync_stale_signals(catalog: SourceCatalog, signal_store: SignalStore, *, agents,
                             knowledge=None, now: datetime | None = None,
                             interval_minutes: int = DEFAULT_INTERVAL_MINUTES) -> dict:
    """Sweep every Intelligence Worker agent and refresh any connected, due pollable source.

    Mirrors app.modules.sales_intelligence.scheduler.scan_due_sources's shape: one failure never
    aborts the sweep, and the summary is structured so both a human and a test can tell what
    happened without reading logs."""
    now = now or datetime.now(timezone.utc)
    pollable = set(catalog.pollable_keys())
    considered = synced = skipped = failed = 0

    all_agents = await agents.list_all()
    for agent in all_agents:
        if getattr(agent, "atype", None) != "intelligence":
            continue
        considered += 1
        cfg = agent.config or {}

        if "github" in pollable and cfg.get("github_credentials_added"):
            credential = _github_credential(cfg)
            repo_allowlist = cfg.get("github_repo_allowlist") or []
            if credential and repo_allowlist:
                try:
                    due, since = await _is_signal_source_due(
                        signal_store, agent.tenant, agent.id, source="github",
                        interval_minutes=interval_minutes, now=now)
                    if due:
                        await ingest_source(
                            agent.tenant, agent.id, "github",
                            {"repo_allowlist": repo_allowlist,
                             "watched_branches": cfg.get("github_watched_branches") or []},
                            credential, catalog=catalog, signal_store=signal_store,
                            knowledge=knowledge, since=since)
                        synced += 1
                    else:
                        skipped += 1
                except Exception:  # noqa: BLE001 - one agent's failure must not abort the sweep
                    failed += 1
                    logger.exception(
                        "intelligence scheduler: github sync failed",
                        extra={"tenant": agent.tenant, "agent_id": agent.id})

        if "qiko_track" in pollable and cfg.get("qiko_track_credentials_added"):
            credential = _qiko_track_credential(cfg)
            project_keys = cfg.get("qiko_track_project_keys") or []
            base_url = cfg.get("qiko_track_base_url") or ""
            if credential and project_keys and base_url:
                try:
                    due, since = await _is_signal_source_due(
                        signal_store, agent.tenant, agent.id, source="qiko_track",
                        interval_minutes=interval_minutes, now=now)
                    if due:
                        await ingest_source(
                            agent.tenant, agent.id, "qiko_track",
                            {"project_keys": project_keys, "base_url": base_url},
                            credential, catalog=catalog, signal_store=signal_store,
                            knowledge=knowledge, since=since)
                        synced += 1
                    else:
                        skipped += 1
                except Exception:  # noqa: BLE001 - one agent's failure must not abort the sweep
                    failed += 1
                    logger.exception(
                        "intelligence scheduler: qiko_track sync failed",
                        extra={"tenant": agent.tenant, "agent_id": agent.id})

        if "ga4" in pollable and cfg.get("ga4_credentials_added"):
            try:
                due, since = await _is_signal_source_due(
                    signal_store, agent.tenant, agent.id, source="ga4",
                    interval_minutes=interval_minutes, now=now)
                if due:
                    # No per-agent config: GA4 always resolves the property and credential
                    # from Settings (see GA4Connector._client).
                    await ingest_source(
                        agent.tenant, agent.id, "ga4",
                        {},
                        "", catalog=catalog, signal_store=signal_store, knowledge=knowledge,
                        since=since)
                    synced += 1
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001 - one agent's failure must not abort the sweep
                failed += 1
                logger.exception(
                    "intelligence scheduler: ga4 sync failed",
                    extra={"tenant": agent.tenant, "agent_id": agent.id})

    summary = {"considered": considered, "synced": synced, "skipped": skipped, "failed": failed}
    logger.info("intelligence scheduler: sync sweep complete", extra=summary)
    return summary
