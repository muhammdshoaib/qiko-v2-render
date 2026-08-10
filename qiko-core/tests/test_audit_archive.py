"""The off-database copy of the audit trail, and its tamper-evidence digest.

The question behind the word "immutable" in a tender reduces to two properties: the application cannot
alter historic rows, and a second copy exists that the people who administer the primary database cannot
alter. A per-row hash chain answers neither on its own, because the head of the chain lives in the same
database as the rows.
"""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone

from app.modules.audit import registry
from app.modules.audit.archive import (
    DIGESTED_FIELDS,
    EXCLUDED_FROM_DIGEST,
    build_day_export,
    day_bounds,
    verify,
)
from app.modules.audit.service import AuditEvent, InMemoryAuditStore, build_row


def _row(action=registry.LOGIN_FAILED, at=None, **over) -> dict:
    row = build_row(AuditEvent(action=action, target_id="t", target_label="t@x.invalid",
                               occurred_at=at or datetime(2026, 8, 5, 12, tzinfo=timezone.utc)))
    row.update(over)
    return row


class _Storage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, tenant, key, data, content_type="application/octet-stream") -> str:
        self.objects[key] = data
        return f"memory://{tenant}/{key}"


class _Archive:
    def __init__(self) -> None:
        self.days: dict[str, dict] = {}

    async def latest(self):
        if not self.days:
            return None
        return self.days[max(self.days)]

    async def record(self, *, day, row_count, digest, previous_digest, object_key):
        self.days[day] = {"day": day, "digest": digest, "row_count": row_count,
                          "object_key": object_key, "previous_digest": previous_digest}


def test_the_digest_detects_a_changed_row():
    """The whole point. Any alteration inside a covered day changes that day's digest, and the digest is
    held outside the database."""
    rows = [_row(target_id="a"), _row(target_id="b")]
    export = build_day_export(rows, date(2026, 8, 5))
    assert verify(export, rows)

    tampered = [dict(rows[0], target_id="c"), rows[1]]
    assert not verify(export, tampered)


def test_the_digest_is_stable_regardless_of_the_order_rows_arrive_in():
    """Sorted by (occurred_at, event_id), not by primary key: the key is assigned at insert and
    occurred_at when the event happened, so a digest computed in key order would differ between an export
    and a re-export of the same day."""
    early = _row(at=datetime(2026, 8, 5, 9, tzinfo=timezone.utc))
    late = _row(at=datetime(2026, 8, 5, 18, tzinfo=timezone.utc))
    assert (build_day_export([early, late], date(2026, 8, 5)).digest
            == build_day_export([late, early], date(2026, 8, 5)).digest)


def test_the_days_are_chained_so_a_deleted_day_is_visible():
    """Deleting a whole object is the easier attack than editing a row inside one, and a per-day digest
    with no link would not notice."""
    monday = build_day_export([_row()], date(2026, 8, 3))
    tuesday = build_day_export([_row()], date(2026, 8, 4), previous_digest=monday.digest)
    assert tuesday.previous_digest == monday.digest
    # Recomputing Tuesday against a different predecessor gives a different answer, which is what makes
    # a missing Monday detectable.
    assert build_day_export([_row()], date(2026, 8, 4), previous_digest="0" * 64).digest != tuesday.digest


def test_the_digest_excludes_what_erasure_legitimately_rewrites():
    """An erasure request rewrites identifiers in place and must not be indistinguishable from tampering.

    This is a real trade and the module states it: an attacker who rewrites an identifier through the
    erasure path leaves the digest intact. The compensating control is that erasure is audited, gated on
    manage_admins, and records the row count it touched. A tamper-evidence claim that does not state its
    own boundary is worse than no claim.
    """
    assert not set(DIGESTED_FIELDS) & set(EXCLUDED_FROM_DIGEST)
    rows = [_row()]
    export = build_day_export(rows, date(2026, 8, 5))
    pseudonymised = [dict(rows[0], target_label=None, actor_label=None, source_ip=None,
                          subject_pseudonym="9f2c", pseudonymised_at=datetime.now(timezone.utc))]
    assert verify(export, pseudonymised), "erasure must not read as tampering"


def test_the_digested_field_list_is_explicit():
    """Not "everything": adding a column would otherwise change every historic digest and make old
    exports unverifiable."""
    assert "event_id" in DIGESTED_FIELDS and "action" in DIGESTED_FIELDS
    assert "changes" not in DIGESTED_FIELDS, "a JSON column's serialisation is not stable enough"


def test_a_day_is_half_open_so_midnight_belongs_to_one_day():
    start, end = day_bounds(date(2026, 8, 5))
    assert start == datetime(2026, 8, 5, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 6, tzinfo=timezone.utc)


def test_the_export_writes_the_manifest_in_the_same_object_as_the_rows():
    """A retrieval must not be able to get one without the other."""
    from app.tasks.jobs import export_audit_archive

    store = InMemoryAuditStore()
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    asyncio.run(store.add(_row(at=yesterday)))
    storage, archive = _Storage(), _Archive()

    result = asyncio.run(export_audit_archive(store, archive, storage))
    assert result["row_count"] == 1
    body = storage.objects[result["object_key"]].decode().splitlines()
    manifest = json.loads(body[0])["manifest"]
    assert manifest["digest"] == result["digest"]
    assert manifest["row_count"] == 1
    assert json.loads(body[1])["action"] == registry.LOGIN_FAILED


def test_yesterday_not_today():
    """Exporting a day still in progress produces an object that is incomplete the moment it is written,
    and a digest that legitimately changes on re-export, which destroys the only property it has."""
    from app.tasks.jobs import export_audit_archive

    store = InMemoryAuditStore()
    asyncio.run(store.add(_row(at=datetime.now(timezone.utc))))  # today
    result = asyncio.run(export_audit_archive(store, _Archive(), _Storage()))
    assert result["day"] == (date.today() - timedelta(days=1)).isoformat()
    assert result["row_count"] == 0, "today's rows are not yet eligible"


def test_an_empty_day_is_still_exported():
    """An absent object is indistinguishable from a deleted one, and the chain only works if every day is
    a link."""
    from app.tasks.jobs import export_audit_archive

    storage, archive = _Storage(), _Archive()
    result = asyncio.run(export_audit_archive(InMemoryAuditStore(), archive, storage))
    assert result["row_count"] == 0
    assert result["object_key"] in storage.objects
    assert archive.days


def test_re_exporting_an_unchanged_day_produces_the_same_digest():
    """Which is what makes a CHANGED digest on re-export the tamper signal, rather than noise."""
    from app.tasks.jobs import export_audit_archive

    store = InMemoryAuditStore()
    asyncio.run(store.add(_row(at=datetime.now(timezone.utc) - timedelta(days=1))))
    archive = _Archive()
    first = asyncio.run(export_audit_archive(store, archive, _Storage()))
    # A fresh archive, so the chain starts the same way and only the rows decide the digest.
    second = asyncio.run(export_audit_archive(store, _Archive(), _Storage()))
    assert first["digest"] == second["digest"]


def test_the_export_runs_before_retention_deletes_anything():
    """Exporting after the delete would lose exactly the rows the archive exists to keep."""
    from app.tasks.worker import CRON_JOBS

    jobs = {getattr(job, "name", ""): job for job in CRON_JOBS}
    export, retention = jobs["audit:export_archive"], jobs["audit:apply_retention"]

    def at(job):
        # arq normalises hour/minute to a set OR keeps the int it was given, depending on version.
        pick = lambda v: min(v) if isinstance(v, (set, frozenset, list, tuple)) else v  # noqa: E731
        return (pick(job.hour), pick(job.minute))

    assert at(export) < at(retention)
