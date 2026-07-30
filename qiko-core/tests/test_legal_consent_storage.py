import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import BigInteger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import ConsentRecord as ConsentRecordRow
from app.db.models import PendingSignup as PendingSignupRow
from app.db.stores import SqlConsentStore, SqlPendingSignupStore
from app.modules.consent.models import CURRENT_POLICY_RELEASES, ConsentChoices
from app.modules.consent.service import ConsentService
from app.modules.identity.pending_signup import InMemoryPendingSignupStore, make_pending_signup
from app.modules.identity.rbac import Role


def _migrated_database(tmp_path) -> Path:
    database = tmp_path / "legal.db"
    os.environ["ALEMBIC_URL"] = f"sqlite:///{database}"
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        os.environ.pop("ALEMBIC_URL", None)
    return database


def test_pending_invite_version_uses_big_integer():
    assert isinstance(PendingSignupRow.__table__.c.invite_version.type, BigInteger)


def test_consent_revisions_use_big_integer_for_millisecond_values():
    assert isinstance(ConsentRecordRow.__table__.c.revision.type, BigInteger)
    assert isinstance(ConsentRecordRow.__table__.c.client_revision.type, BigInteger)


def test_policy_release_digests_match_exact_current_legal_tsx_files():
    repository = Path(__file__).resolve().parents[2]
    files = {
        "terms-2026-07-24": repository / "frontend/apps/creator/app/terms/page.tsx",
        "privacy-2026-07-24": repository / "frontend/apps/creator/app/privacy/page.tsx",
        "cookies-2026-07-24": repository / "frontend/apps/creator/app/cookies/page.tsx",
    }
    for release_id, path in files.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == CURRENT_POLICY_RELEASES[release_id][1]


def test_sqlite_rejects_policy_and_consent_updates_and_deletes(tmp_path):
    database = _migrated_database(tmp_path)
    connection = sqlite3.connect(database)
    releases = dict(connection.execute("SELECT id, content_sha256 FROM policy_releases"))
    assert releases == {key: value[1] for key, value in CURRENT_POLICY_RELEASES.items()}
    connection.execute(
        """INSERT INTO consent_records
        (id, decision_id, revision, client_revision, key_version, subject_hmac, preferences, analytics,
         marketing, source, action, terms_release_id, privacy_release_id, cookies_release_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "record-1", "decision-1", 1, 1, "v1", "a" * 64,
            False, False, False, "anonymous", "reject",
            "terms-2026-07-24", "privacy-2026-07-24", "cookies-2026-07-24",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    connection.commit()

    for statement in (
        "UPDATE policy_releases SET policy_type='privacy' WHERE id='terms-2026-07-24'",
        "DELETE FROM policy_releases WHERE id='terms-2026-07-24'",
        "UPDATE consent_records SET analytics=1 WHERE id='record-1'",
        "DELETE FROM consent_records WHERE id='record-1'",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(statement)
    connection.close()


async def test_sql_consent_store_persists_append_only_history(tmp_path):
    database = _migrated_database(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    service = ConsentService(store=SqlConsentStore(async_sessionmaker(engine, expire_on_commit=False)))
    first = await service.record(
        namespace="anonymous",
        identifier="browser-generated-id-12345",
        choices=ConsentChoices(False, False, False),
        source="anonymous",
    )
    second = await service.record(
        namespace="anonymous",
        identifier="browser-generated-id-12345",
        choices=ConsentChoices(True, False, False),
        source="anonymous",
    )
    assert first.action == "reject" and second.action == "update"
    assert (await service.latest(
        namespace="anonymous", identifier="browser-generated-id-12345"
    )).id == second.id
    await engine.dispose()

    connection = sqlite3.connect(database)
    rows = connection.execute(
        "SELECT subject_hmac, source, action FROM consent_records ORDER BY created_at, id"
    ).fetchall()
    connection.close()
    assert len(rows) == 2
    assert rows[0][0] == rows[1][0] != "browser-generated-id-12345"
    assert [row[2] for row in rows] == ["reject", "update"]


async def test_pending_signup_does_not_replace_unexpired_credentials():
    store = InMemoryPendingSignupStore()
    first, _ = make_pending_signup(
        user_id="first", email="same" + "@" + "example.test", password_hash="victim-hash",
        tenant="tenant", role=Role.owner, terms_release_id="terms-2026-07-24",
        privacy_release_id="privacy-2026-07-24", cookies_release_id="cookies-2026-07-24")
    competing, _ = make_pending_signup(
        user_id="second", email=first.email, password_hash="attacker-hash",
        tenant="attacker", role=Role.viewer, terms_release_id="terms-2026-07-24",
        privacy_release_id="privacy-2026-07-24", cookies_release_id="cookies-2026-07-24")
    assert await store.put(first) is True
    assert await store.put(competing) is False
    stored = await store.get(first.email)
    assert stored.user_id == first.user_id and stored.password_hash == "victim-hash"


async def test_pending_signup_invalidates_after_five_wrong_codes():
    store = InMemoryPendingSignupStore()
    pending, code = make_pending_signup(
        user_id="future", email="attempts" + "@" + "example.test", password_hash="hash",
        tenant="tenant", role=Role.owner, terms_release_id="terms-2026-07-24",
        privacy_release_id="privacy-2026-07-24", cookies_release_id="cookies-2026-07-24")
    await store.put(pending)
    for _ in range(5):
        assert await store.consume(pending.email, "000000") is None
    assert await store.consume(pending.email, code) is None
    assert await store.get(pending.email) is None


async def test_sql_pending_signup_purge_removes_untouched_expired_rows(tmp_path):
    database = _migrated_database(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    store = SqlPendingSignupStore(async_sessionmaker(engine, expire_on_commit=False))
    pending, _ = make_pending_signup(
        user_id="expired-user", email="expired" + "@" + "example.test", password_hash="hash",
        tenant="tenant", role=Role.owner, terms_release_id="terms-2026-07-24",
        privacy_release_id="privacy-2026-07-24", cookies_release_id="cookies-2026-07-24", ttl=-1)
    await store.put(pending)
    assert await store.purge_expired() == 1
    assert await store.get(pending.email) is None
    await engine.dispose()


async def test_sql_signup_finalization_is_atomic_and_retry_safe(tmp_path):
    database = _migrated_database(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    store = SqlPendingSignupStore(async_sessionmaker(engine, expire_on_commit=False))
    pending, code = make_pending_signup(
        user_id="atomic-user", email="atomic" + "@" + "example.test", password_hash="hash",
        tenant="atomic-tenant", role=Role.owner, terms_release_id="terms-2026-07-24",
        privacy_release_id="privacy-2026-07-24", cookies_release_id="cookies-2026-07-24")
    await store.put(pending)
    first = await store.finalize_signup(
        pending.email, code, "verified-hash", "terms-2026-07-24",
        "privacy-2026-07-24", "cookies-2026-07-24")
    retry = await store.finalize_signup(
        pending.email, code, "verified-hash", "terms-2026-07-24",
        "privacy-2026-07-24", "cookies-2026-07-24")
    assert first and retry and first[1] is True and retry[1] is False
    assert first[0].completed_team_id == retry[0].completed_team_id
    await engine.dispose()
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT password_hash FROM users WHERE email = ?", (pending.email,)).fetchone()[0] == "verified-hash"
    assert connection.execute("SELECT COUNT(*) FROM teams WHERE tenant_id = ?", (pending.tenant,)).fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM consent_records WHERE decision_id = ?",
                              (f"signup:{pending.user_id}",)).fetchone()[0] == 1
    connection.close()


async def test_sql_pending_signup_persists_and_code_is_one_time(tmp_path):
    database = _migrated_database(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlPendingSignupStore(sessionmaker)
    pending, code = make_pending_signup(
        user_id="future-user",
        email="pending" + "@" + "example.test",
        password_hash="not-a-login-row",
        tenant="future-tenant",
        role=Role.owner,
        terms_release_id="terms-2026-07-24",
        privacy_release_id="privacy-2026-07-24",
        cookies_release_id="cookies-2026-07-24",
    )
    await store.put(pending)
    await engine.dispose()

    restarted = create_async_engine(f"sqlite+aiosqlite:///{database}")
    restarted_store = SqlPendingSignupStore(async_sessionmaker(restarted, expire_on_commit=False))
    assert (await restarted_store.get("pending" + "@" + "example.test")).user_id == "future-user"
    assert await restarted_store.consume("pending" + "@" + "example.test", "000000") is None
    assert (await restarted_store.consume("pending" + "@" + "example.test", code)).user_id == "future-user"
    await restarted_store.delete("pending" + "@" + "example.test")
    assert await restarted_store.consume("pending" + "@" + "example.test", code) is None
    await restarted.dispose()
