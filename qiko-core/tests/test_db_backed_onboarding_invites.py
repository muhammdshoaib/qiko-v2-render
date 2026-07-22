"""Durable (Postgres-backed) password-reset OTP store + pending team-invite store.

SqlOtpStore and SqlPendingInviteStore are drop-in async replacements for the in-memory stores,
swapped in under USE_DB_STORES so a reset code / outstanding invite survives a redeploy. Run
against SQLite (aiosqlite) here, same as the other DB-backed store tests."""
import importlib.util
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.stores import SqlOtpStore, SqlPendingInviteStore
from app.modules.identity.rbac import Role


async def _sessionmaker(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_sql_otp_store_issue_and_verify(tmp_path):
    store = SqlOtpStore(await _sessionmaker(tmp_path / "otp.db"))
    code = await store.issue("User@Qiko.ai")
    assert code.isdigit() and len(code) == 6
    # A wrong code never verifies (and does not consume the outstanding code).
    wrong = "000001" if code != "000001" else "000002"
    assert await store.verify("user@qiko.ai", wrong) is False
    # The correct code verifies once, case-insensitively on the email.
    assert await store.verify("USER@qiko.ai", code) is True
    # Single-use: the code is consumed (deleted) on success, so a replay fails.
    assert await store.verify("user@qiko.ai", code) is False


async def test_sql_otp_store_rejects_expired(tmp_path):
    store = SqlOtpStore(await _sessionmaker(tmp_path / "otp_exp.db"))
    expired = await store.issue("u@qiko.ai", ttl=-1)  # already past its expiry
    assert await store.verify("u@qiko.ai", expired) is False


async def test_sql_otp_store_stores_hash_not_plaintext(tmp_path):
    """Defence in depth: the plaintext code must never be at rest -- only a keyed hash."""
    from sqlalchemy import select

    from app.db.models import PasswordResetOtp as Row

    sm = await _sessionmaker(tmp_path / "otp_hash.db")
    store = SqlOtpStore(sm)
    code = await store.issue("secret@qiko.ai")
    async with sm() as s:
        row = (await s.execute(select(Row))).scalars().one()
    assert row.code_hash != code
    assert len(row.code_hash) == 64  # sha256 hex digest


async def test_sql_pending_invite_store_round_trip(tmp_path):
    store = SqlPendingInviteStore(await _sessionmaker(tmp_path / "inv.db"))
    invite = await store.add("idg", "New.Person@idg.com", Role.admin)
    assert invite.email == "new.person@idg.com" and invite.role is Role.admin
    assert [i.email for i in await store.list("idg")] == ["new.person@idg.com"]
    got = await store.get("idg", "new.person@idg.com")
    assert got is not None and got.role is Role.admin
    # Tenant isolation: another tenant never sees idg's invite.
    assert await store.list("acme") == []
    assert await store.get("acme", "new.person@idg.com") is None
    # Remove is idempotent-safe: true once, false thereafter.
    assert await store.remove("idg", "new.person@idg.com") is True
    assert await store.remove("idg", "new.person@idg.com") is False
    assert await store.list("idg") == []


def test_migration_0023_imports_and_chains():
    # Loaded by file path: the versions dir is not an importable package (and its module name
    # starts with a digit), so spec_from_file_location is the standard way to import it.
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0023_otp_and_pending_invites.py"
    spec = importlib.util.spec_from_file_location("mig_0023", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0023_otp_and_pending_invites"
    assert mod.down_revision == "0022_rfp_pack_source_documents"
    assert callable(mod.upgrade) and callable(mod.downgrade)
