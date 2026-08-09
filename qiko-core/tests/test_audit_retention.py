"""Leg E4: retention and erasure for the audit trail.

The trail accumulated emails, IP addresses and user agents with no expiry, no pseudonymisation and no
erasure path, while the model docstring claimed the source address was nulled after six months. The
security review named that as the same defect class as everything else it found: a documented property
with nothing implementing it.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.modules.audit import registry
from app.modules.audit.retention import (
    EVENT_RETENTION_DAYS,
    NETWORK_RETENTION_DAYS,
    audit_subject_pseudonym,
    cutoffs,
)
from app.modules.audit.service import AuditEvent, build_row
from app.modules.identity import csrf
from app.modules.identity.admin_rbac import Capability
from tests.helpers import auth_cookies, bootstrap_admin

ADMIN = "retention-admin.invalid"


def _admin(client) -> tuple[dict, dict]:
    bootstrap_admin(client, ADMIN)
    token = csrf.generate_csrf_token()
    return ({**auth_cookies("platform", "owner", email=ADMIN), csrf.CSRF_COOKIE: token},
            {csrf.CSRF_HEADER: token})


def _plant(client, *, action=registry.LOGIN_FAILED, days_ago=0, email="subject@acme.invalid"):
    row = build_row(AuditEvent(
        action=action, target_id=email, target_label=email, actor_label=email,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=days_ago)))
    row["source_ip"] = "203.0.113.9"
    row["user_agent"] = "Mozilla/5.0"
    asyncio.run(client.app.state.audit.add(row))
    return row


# --- retention ------------------------------------------------------------------------------------

def test_the_two_cutoffs_are_thirteen_and_six_months():
    """13 months covers an annual Type II observation window plus the sample requests that arrive after
    it closes, and sits above the 12-month floor PCI DSS 10.5.1 states. Six months for network
    identifiers is CNIL's baseline for traceability logs."""
    assert EVENT_RETENTION_DAYS == 396
    assert NETWORK_RETENTION_DAYS == 183
    events, network = cutoffs(datetime(2026, 8, 1, tzinfo=timezone.utc))
    assert events < network < datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_an_expired_event_is_deleted_and_a_recent_one_is_not(client):
    _plant(client, days_ago=400)
    _plant(client, days_ago=10)
    result = asyncio.run(client.app.state.audit.apply_retention())
    assert result["events_deleted"] == 1
    assert len(client.app.state.audit.rows) == 1


def test_the_address_expires_before_the_event_does(client):
    """Nulling in place costs a field rather than an event, so the completeness the trail relies on is
    untouched. Deleting the event to remove the address would be the wrong trade."""
    _plant(client, days_ago=200)
    result = asyncio.run(client.app.state.audit.apply_retention())
    assert result["events_deleted"] == 0, "the event is still inside its window"
    assert result["addresses_cleared"] == 1
    row = client.app.state.audit.rows[0]
    assert row["source_ip"] is None and row["user_agent"] is None
    assert row["action"] == registry.LOGIN_FAILED, "the event itself survives"


def test_the_retention_run_records_itself(client):
    """A policy nobody can show running is a paragraph rather than a control. The counts are what an
    auditor asks for when they check a stated policy is implemented."""
    from app.tasks.jobs import apply_audit_retention

    _plant(client, days_ago=400)
    asyncio.run(apply_audit_retention(client.app.state.audit))
    recorded = [r for r in client.app.state.audit.rows
                if r["action"] == registry.RETENTION_APPLIED]
    assert len(recorded) == 1
    assert recorded[0]["changes"]["events_deleted"]["to"] == 1
    assert recorded[0]["actor_type"] == "job"


def test_a_run_that_deletes_nothing_still_leaves_evidence(client):
    from app.tasks.jobs import apply_audit_retention

    asyncio.run(apply_audit_retention(client.app.state.audit))
    assert [r for r in client.app.state.audit.rows if r["action"] == registry.RETENTION_APPLIED]


def test_the_retention_job_is_scheduled():
    """It exists as code only if something runs it."""
    from app.tasks.worker import CRON_JOBS

    assert any(getattr(job, "name", "") == "audit:apply_retention" for job in CRON_JOBS)


def test_the_policy_endpoint_reads_the_same_constants_the_job_uses(client):
    """A stated policy that differs from the implemented one is the specific thing both SOC 2 and a data
    protection review check for, so the number an operator is shown comes from the code."""
    cookies, _ = _admin(client)
    body = client.get("/api/v1/admin/audit/retention", cookies=cookies).json()
    assert body["event_retention_days"] == EVENT_RETENTION_DAYS
    assert body["network_retention_days"] == NETWORK_RETENTION_DAYS


# --- erasure --------------------------------------------------------------------------------------

def test_erasure_pseudonymises_and_never_deletes(client):
    """A gap in an audit trail is indistinguishable from tampering."""
    cookies, headers = _admin(client)
    _plant(client, email="erase.me@acme.invalid")
    _plant(client, email="keep.me@acme.invalid")

    response = client.post("/api/v1/admin/audit/erase", cookies=cookies, headers=headers,
                           json={"identifier": "erase.me@acme.invalid", "request_ref": "DSAR-2026-14"})
    assert response.status_code == 200
    assert response.json()["rows_pseudonymised"] == 1

    rows = client.app.state.audit.rows
    assert len(rows) >= 2, "no row was removed"
    assert not any("erase.me@acme.invalid" in str(row) for row in rows)
    assert any("keep.me@acme.invalid" in str(row) for row in rows), "only the subject was touched"


def test_the_erased_row_keeps_everything_that_is_not_an_identifier(client):
    cookies, headers = _admin(client)
    _plant(client, email="erase.me@acme.invalid", days_ago=3)
    before = dict(client.app.state.audit.rows[0])

    client.post("/api/v1/admin/audit/erase", cookies=cookies, headers=headers,
                json={"identifier": "erase.me@acme.invalid", "request_ref": "DSAR-1"})
    after = client.app.state.audit.rows[0]
    assert after["action"] == before["action"]
    assert after["occurred_at"] == before["occurred_at"]
    assert after["outcome"] == before["outcome"]
    assert after["subject_pseudonym"] and after["pseudonymised_at"]
    assert after["source_ip"] is None, "the address goes with the identity"


def test_the_erasure_event_does_not_recreate_the_address_it_removed(client):
    """The circularity that catches most implementations. The row proves an erasure occurred, when, by
    whom, how many rows and against which request, without holding the erased identifier."""
    cookies, headers = _admin(client)
    _plant(client, email="erase.me@acme.invalid")
    client.post("/api/v1/admin/audit/erase", cookies=cookies, headers=headers,
                json={"identifier": "erase.me@acme.invalid", "request_ref": "DSAR-2026-14"})

    event = next(r for r in client.app.state.audit.rows
                 if r["action"] == registry.SUBJECT_ERASED)
    assert "erase.me@acme.invalid" not in str(event)
    assert event["target_id"] == audit_subject_pseudonym("erase.me@acme.invalid")
    assert event["changes"]["request_ref"]["to"] == "DSAR-2026-14"
    assert event["changes"]["rows_pseudonymised"]["to"] == 1


def test_the_pseudonym_is_stable_keyed_and_not_the_consent_one():
    """Stable so a subject's rows stay linkable to each other after erasure. Keyed so the log alone
    cannot be reversed. A different namespace from consent so holding one table does not let you
    correlate against the other."""
    from app.modules.consent.service import pseudonymous_subject

    first = audit_subject_pseudonym("Erase.Me@acme.invalid")
    assert first == audit_subject_pseudonym("erase.me@acme.invalid"), "case-insensitive and stable"
    assert first != audit_subject_pseudonym("other@acme.invalid")
    assert "acme.invalid" not in first
    assert first != pseudonymous_subject("consent-subject", "erase.me@acme.invalid")[:64]


def test_erasure_needs_manage_admins_and_csrf(client):
    """It rewrites the evidence trail, which is a higher privilege than acting on a customer."""
    cookies, headers = _admin(client)
    client.put("/api/v1/admin/org/weak@invalid", cookies=cookies, headers=headers,
               json={"role": "viewer", "capabilities": [Capability.view_audit.value,
                                                        Capability.manage_customers.value]})
    weak = auth_cookies("platform", "viewer", email="weak@invalid")
    token = csrf.generate_csrf_token()
    assert client.post("/api/v1/admin/audit/erase",
                       cookies={**weak, csrf.CSRF_COOKIE: token},
                       headers={csrf.CSRF_HEADER: token},
                       json={"identifier": "x@y.invalid", "request_ref": "r"}).status_code == 403
    assert client.post("/api/v1/admin/audit/erase", cookies=cookies,
                       json={"identifier": "x@y.invalid", "request_ref": "r"}).status_code == 403


def test_a_request_reference_is_required(client):
    """An erasure with no reference is one nobody can justify later, and the reference is what holds the
    mapping back to the person, outside this table."""
    cookies, headers = _admin(client)
    assert client.post("/api/v1/admin/audit/erase", cookies=cookies, headers=headers,
                       json={"identifier": "x@y.invalid"}).status_code == 422


def test_the_model_no_longer_claims_something_nothing_does():
    """The docstring said the address was nulled after six months while nothing nulled it."""
    import inspect

    from app.db.models import AuditEventRow

    source = inspect.getsource(AuditEventRow)
    assert "six months" in source
    assert "audit:apply_retention" in source, "the claim must name what enforces it"


def test_erasure_covers_every_field_that_can_hold_the_identifier(client):
    """The first version of this leg missed `message`, which is rendered FROM the labels and is the one
    field a human actually reads. An erasure that leaves the address in the readable sentence is worse
    than no erasure, because it reports success.

    Enumerated rather than spot-checked, so the next field added to the table has to be considered.
    """
    cookies, headers = _admin(client)
    subject = "erase.me@acme.invalid"
    _plant(client, action=registry.TENANT_ROLE_CHANGED, email=subject)
    planted = client.app.state.audit.rows[0]
    assert subject in planted["message"], "the fixture must actually exercise the sentence"

    client.post("/api/v1/admin/audit/erase", cookies=cookies, headers=headers,
                json={"identifier": subject, "request_ref": "DSAR-1"})

    row = client.app.state.audit.rows[0]
    for field in ("target_id", "target_label", "actor_id", "actor_label", "message",
                  "source_ip", "user_agent", "reason"):
        assert subject not in str(row.get(field) or ""), f"{field} still holds the identifier"
    # And nothing anywhere else in the row either, including the structured payloads.
    assert subject not in str(row)


def test_the_erasure_and_its_record_share_a_transaction():
    """The first version wrote the record afterwards, and the behavioural coverage test caught it: an
    erasure that lands without its own record is the one case a regulator asks about directly.

    Unlike the other CRITICAL actions this needed no restructuring, because the erasure and its audit
    row live in the same store. Counting inside that transaction is also what lets the record carry the
    real row count rather than omitting it.
    """
    import inspect

    from app.db.stores import SqlAuditStore

    source = inspect.getsource(SqlAuditStore.pseudonymise_subject)
    assert "async with self.sessionmaker() as s, s.begin():" in source
    assert "s.add(AuditEventRow(**audit_row(affected)))" in source
    # The count is taken before the update, inside the same transaction.
    assert source.index("select(func.count())") < source.index("update(AuditEventRow)")
    assert registry.spec_for(registry.SUBJECT_ERASED).durability == registry.CRITICAL


def test_the_erasure_record_carries_the_real_count(client):
    cookies, headers = _admin(client)
    for _ in range(3):
        _plant(client, email="many@acme.invalid")
    _plant(client, email="other@acme.invalid")

    response = client.post("/api/v1/admin/audit/erase", cookies=cookies, headers=headers,
                           json={"identifier": "many@acme.invalid", "request_ref": "DSAR-3"})
    assert response.json()["rows_pseudonymised"] == 3
    event = next(r for r in client.app.state.audit.rows if r["action"] == registry.SUBJECT_ERASED)
    assert event["changes"]["rows_pseudonymised"]["to"] == 3
