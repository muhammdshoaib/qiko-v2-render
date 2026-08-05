"""The provisioning CLI writes the highest privilege in the system, so its guards are tested:
dry-run by default, live needs a repeated confirmation, unknown capabilities are refused, and the
write is audited."""
import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.stores import SqlAdminOrgStore

import scripts.provision_platform_admin as cli

EMAIL = "ops.cli@invalid"


@pytest.fixture
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path / 'admins.db'}"

    async def create() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create())
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("USE_DB_STORES", "true")
    monkeypatch.setenv("ENVIRONMENT", "preprod")
    return url


def _identity(url: str, email: str):
    async def read():
        engine = create_async_engine(url)
        try:
            return await SqlAdminOrgStore(async_sessionmaker(engine)).get_identity(email)
        finally:
            await engine.dispose()

    return asyncio.run(read())


def test_dry_run_is_the_default_and_writes_nothing(db, capsys):
    assert cli.main(["--email", EMAIL, "--role", "super_admin"]) == 0
    assert capsys.readouterr().out.startswith("DRY_RUN")
    assert _identity(db, EMAIL) is None


def test_apply_creates_the_admin_and_audits_it(db, capsys):
    assert cli.main(["--email", EMAIL, "--role", "viewer",
                     "--capabilities", "view_customers,manage_workers",
                     "--actor", "operator@invalid", "--apply"]) == 0
    assert capsys.readouterr().out.startswith("APPLIED")

    identity = _identity(db, EMAIL)
    assert identity is not None and identity.role.value == "viewer"
    assert sorted(c.value for c in identity.capabilities) == ["manage_workers", "view_customers"]

    async def read_audit():
        engine = create_async_engine(db)
        try:
            return await SqlAdminOrgStore(async_sessionmaker(engine)).list_audit()
        finally:
            await engine.dispose()

    entries = asyncio.run(read_audit())
    assert entries and entries[0].email == EMAIL
    assert entries[0].changed_by_email == "operator@invalid"
    assert entries[0].previous_role is None and entries[0].role == "viewer"


def test_reapplying_the_same_grant_reports_no_changes(db, capsys):
    cli.main(["--email", EMAIL, "--role", "viewer", "--apply"])
    capsys.readouterr()
    assert cli.main(["--email", EMAIL, "--role", "viewer", "--apply"]) == 0
    assert capsys.readouterr().out.startswith("NO_CHANGES")


def test_live_requires_the_email_typed_twice(db, monkeypatch, capsys):
    monkeypatch.setenv("ENVIRONMENT", "live")
    assert cli.main(["--email", EMAIL, "--role", "super_admin", "--apply"]) == 2
    assert "confirm-email" in capsys.readouterr().err
    assert _identity(db, EMAIL) is None

    assert cli.main(["--email", EMAIL, "--role", "super_admin", "--apply",
                     "--confirm-email", "someone.else@invalid"]) == 2
    assert _identity(db, EMAIL) is None


def test_unknown_capability_is_refused_with_the_known_list(db, capsys):
    assert cli.main(["--email", EMAIL, "--role", "viewer",
                     "--capabilities", "view_customers,nope", "--apply"]) == 2
    err = capsys.readouterr().err
    assert "unknown capability" in err and "view_customers" in err
    assert _identity(db, EMAIL) is None


def test_a_malformed_email_is_refused(db, capsys):
    assert cli.main(["--email", "not-an-email", "--role", "viewer", "--apply"]) == 2
    assert "valid address" in capsys.readouterr().err
