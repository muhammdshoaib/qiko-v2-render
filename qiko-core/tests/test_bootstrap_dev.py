import io
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Environment
from app.db.base import Base
from app.db.dev_bootstrap import DevBootstrapError, DevBootstrapResult, bootstrap_dev_admin
from app.db.models import MfaBackupCode, PlatformAdmin, Tenant, User
from app.modules.identity.admin_rbac import AdminRole
from app.modules.identity.rbac import Role
from app.modules.identity.security import verify_password
from scripts import bootstrap_dev


FIRST_PASSWORD = "correct-horse-battery-staple"
SECOND_PASSWORD = "different-horse-battery-staple"


async def _database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bootstrap.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _counts(sessionmaker):
    async with sessionmaker() as session:
        return (
            await session.scalar(select(func.count()).select_from(Tenant)),
            await session.scalar(select(func.count()).select_from(User)),
            await session.scalar(select(func.count()).select_from(PlatformAdmin)),
        )


async def test_first_bootstrap_creates_tenant_owner_and_platform_super_admin(tmp_path):
    sessionmaker, engine = await _database(tmp_path)
    try:
        result = await bootstrap_dev_admin(
            sessionmaker,
            "local-tenant",
            " Local Tenant ",
            " Owner@Example.Test ",
            FIRST_PASSWORD,
        )

        assert result == DevBootstrapResult(
            tenant_created=True,
            user_created=True,
            password_reset=False,
            owner_granted=True,
            super_admin_granted=True,
        )
        async with sessionmaker() as session:
            tenant = await session.get(Tenant, "local-tenant")
            user = await session.scalar(select(User))
            platform_admin = await session.get(PlatformAdmin, "owner@example.test")
            assert tenant.name == "Local Tenant"
            assert (user.email, user.tenant_id, user.role) == (
                "owner@example.test",
                "local-tenant",
                Role.owner.value,
            )
            assert verify_password(FIRST_PASSWORD, user.password_hash)
            assert user.twofa_enabled is False
            assert user.totp_secret is None
            assert platform_admin.role == AdminRole.super_admin.value
    finally:
        await engine.dispose()


async def test_second_bootstrap_is_idempotent_and_preserves_password_and_mfa(tmp_path):
    sessionmaker, engine = await _database(tmp_path)
    try:
        await bootstrap_dev_admin(
            sessionmaker,
            "local-tenant",
            "Local Tenant",
            "owner@example.test",
            FIRST_PASSWORD,
        )
        async with sessionmaker() as session, session.begin():
            user = await session.scalar(select(User))
            original_hash = user.password_hash
            user.twofa_enabled = True
            user.totp_secret = "encrypted-placeholder"
            session.add(MfaBackupCode(
                user_id=user.id,
                selector="abcd",
                code_hash="backup-code-hash",
            ))

        result = await bootstrap_dev_admin(
            sessionmaker,
            "local-tenant",
            "Local Tenant",
            "OWNER@example.test",
            SECOND_PASSWORD,
        )

        assert result.changes == 0
        assert await _counts(sessionmaker) == (1, 1, 1)
        async with sessionmaker() as session:
            user = await session.scalar(select(User))
            backup_codes = await session.scalar(select(func.count()).select_from(MfaBackupCode))
            assert user.password_hash == original_hash
            assert verify_password(FIRST_PASSWORD, user.password_hash)
            assert not verify_password(SECOND_PASSWORD, user.password_hash)
            assert user.twofa_enabled is True
            assert user.totp_secret == "encrypted-placeholder"
            assert backup_codes == 1
    finally:
        await engine.dispose()


async def test_cross_tenant_email_fails_closed_without_partial_writes(tmp_path):
    sessionmaker, engine = await _database(tmp_path)
    try:
        async with sessionmaker() as session, session.begin():
            session.add(Tenant(id="other-tenant", name="Other Tenant"))
            session.add(User(
                id="other-user",
                email="owner@example.test",
                password_hash="unchanged",
                tenant_id="other-tenant",
                role=Role.owner.value,
            ))

        with pytest.raises(DevBootstrapError, match="another tenant"):
            await bootstrap_dev_admin(
                sessionmaker,
                "local-tenant",
                "Local Tenant",
                "OWNER@example.test",
                FIRST_PASSWORD,
            )

        assert await _counts(sessionmaker) == (1, 1, 0)
        async with sessionmaker() as session:
            assert await session.get(Tenant, "local-tenant") is None
            user = await session.get(User, "other-user")
            assert user.password_hash == "unchanged"
            assert user.tenant_id == "other-tenant"
    finally:
        await engine.dispose()


async def test_reset_password_requires_explicit_flag(tmp_path):
    sessionmaker, engine = await _database(tmp_path)
    try:
        await bootstrap_dev_admin(
            sessionmaker,
            "local-tenant",
            "Local Tenant",
            "owner@example.test",
            FIRST_PASSWORD,
        )

        preserved = await bootstrap_dev_admin(
            sessionmaker,
            "local-tenant",
            "Local Tenant",
            "owner@example.test",
            SECOND_PASSWORD,
        )
        async with sessionmaker() as session:
            user = await session.scalar(select(User))
            assert preserved.password_reset is False
            assert verify_password(FIRST_PASSWORD, user.password_hash)

        reset = await bootstrap_dev_admin(
            sessionmaker,
            "local-tenant",
            "Local Tenant",
            "owner@example.test",
            SECOND_PASSWORD,
            reset_password=True,
        )
        async with sessionmaker() as session:
            user = await session.scalar(select(User))
            assert reset.password_reset is True
            assert verify_password(SECOND_PASSWORD, user.password_hash)
            assert not verify_password(FIRST_PASSWORD, user.password_hash)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "tenant,display_name,email,password",
    [
        ("Bad Tenant", "Local Tenant", "owner@example.test", FIRST_PASSWORD),
        ("local-tenant", "   ", "owner@example.test", FIRST_PASSWORD),
        ("local-tenant", "Local\nTenant", "owner@example.test", FIRST_PASSWORD),
        ("local-tenant", "Local Tenant", "not-an-email", FIRST_PASSWORD),
        ("local-tenant", "Local Tenant", "owner@other@example.test", FIRST_PASSWORD),
        ("local-tenant", "Local Tenant", "owner@example.test", "short"),
        ("local-tenant", "Local Tenant", "owner@example.test", "        "),
    ],
)
async def test_invalid_bootstrap_inputs_fail_before_writes(
    tmp_path, tenant, display_name, email, password
):
    sessionmaker, engine = await _database(tmp_path)
    try:
        with pytest.raises(DevBootstrapError):
            await bootstrap_dev_admin(
                sessionmaker,
                tenant,
                display_name,
                email,
                password,
            )
        assert await _counts(sessionmaker) == (0, 0, 0)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("character", ["\x7f", "\x85", "\x9f", "\u200b"])
async def test_display_name_rejects_every_non_printable_character(tmp_path, character):
    sessionmaker, engine = await _database(tmp_path)
    try:
        with pytest.raises(DevBootstrapError):
            await bootstrap_dev_admin(
                sessionmaker,
                "local-tenant",
                f"Local{character}Tenant",
                "owner@example.test",
                FIRST_PASSWORD,
            )
        assert await _counts(sessionmaker) == (0, 0, 0)
    finally:
        await engine.dispose()


async def test_mixed_case_stored_emails_are_normalized_and_reported(tmp_path):
    sessionmaker, engine = await _database(tmp_path)
    try:
        async with sessionmaker() as session, session.begin():
            session.add(Tenant(id="local-tenant", name="Local Tenant"))
            session.add(User(
                id="existing-user",
                email="Owner@Example.Test",
                password_hash="unchanged",
                tenant_id="local-tenant",
                role=Role.owner.value,
            ))
            session.add(PlatformAdmin(
                email="Owner@Example.Test",
                role=AdminRole.super_admin.value,
            ))

        result = await bootstrap_dev_admin(
            sessionmaker,
            "local-tenant",
            "Local Tenant",
            "owner@example.test",
            FIRST_PASSWORD,
        )

        assert result.user_email_normalized is True
        assert result.admin_email_normalized is True
        assert result.changes == 2
        assert "changes=2" in bootstrap_dev._summary(result)
        assert "user_email_normalized=1" in bootstrap_dev._summary(result)
        assert "admin_email_normalized=1" in bootstrap_dev._summary(result)
        async with sessionmaker() as session:
            user = await session.get(User, "existing-user")
            admin = await session.get(PlatformAdmin, "owner@example.test")
            assert user.email == "owner@example.test"
            assert user.password_hash == "unchanged"
            assert admin.role == AdminRole.super_admin.value
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "environment,use_db_stores",
    [
        (Environment.preprod, True),
        (Environment.live, True),
        (Environment.dev, False),
    ],
)
def test_cli_rejects_non_dev_or_non_database_mode(
    monkeypatch, capsys, environment, use_db_stores
):
    monkeypatch.setattr(
        bootstrap_dev,
        "Settings",
        lambda **_kwargs: SimpleNamespace(
            environment=environment,
            use_db_stores=use_db_stores,
        ),
    )
    monkeypatch.setattr(bootstrap_dev.sys, "stdin", io.StringIO(FIRST_PASSWORD + "\n"))

    result = bootstrap_dev.main([
        "--tenant",
        "local-tenant",
        "--display-name",
        "Local Tenant",
        "--email",
        "owner@example.test",
        "--password-stdin",
    ])

    assert result == 2
    output = capsys.readouterr()
    combined = output.out + output.err
    assert "owner@example.test" not in combined
    assert FIRST_PASSWORD not in combined


def test_cli_reads_password_from_stdin_and_never_prints_it(monkeypatch, capsys):
    received = {}

    async def fake_run(args, settings, password):
        received.update(args=args, settings=settings, password=password)
        return DevBootstrapResult(
            tenant_created=True,
            user_created=True,
            password_reset=False,
            owner_granted=True,
            super_admin_granted=True,
        )

    settings = SimpleNamespace(environment=Environment.dev, use_db_stores=True)
    monkeypatch.setattr(bootstrap_dev, "Settings", lambda **_kwargs: settings)
    monkeypatch.setattr(bootstrap_dev, "_run", fake_run)
    monkeypatch.setattr(bootstrap_dev.sys, "stdin", io.StringIO(FIRST_PASSWORD + "\n"))

    result = bootstrap_dev.main([
        "--tenant",
        "local-tenant",
        "--display-name",
        "Local Tenant",
        "--email",
        "owner@example.test",
        "--password-stdin",
    ])

    assert result == 0
    assert received["password"] == FIRST_PASSWORD
    assert received["settings"] is settings
    assert not hasattr(received["args"], "password")
    output = capsys.readouterr()
    combined = output.out + output.err
    for forbidden in (
        "owner@example.test",
        FIRST_PASSWORD,
        "pbkdf2_sha256",
        "totp",
        "cookie",
        "token",
    ):
        assert forbidden not in combined.lower()


def test_cli_runtime_failure_reports_uncertain_database_state(monkeypatch, capsys):
    async def fail_after_possible_commit(args, settings, password):
        raise RuntimeError("sensitive internal failure")

    monkeypatch.setattr(
        bootstrap_dev,
        "Settings",
        lambda **_kwargs: SimpleNamespace(
            environment=Environment.dev,
            use_db_stores=True,
        ),
    )
    monkeypatch.setattr(bootstrap_dev, "_run", fail_after_possible_commit)
    monkeypatch.setattr(bootstrap_dev.sys, "stdin", io.StringIO(FIRST_PASSWORD + "\n"))

    result = bootstrap_dev.main([
        "--tenant",
        "local-tenant",
        "--display-name",
        "Local Tenant",
        "--email",
        "owner@example.test",
        "--password-stdin",
    ])

    assert result == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "ERROR: development bootstrap did not complete; verify local database state\n"
    )
    assert "no changes were committed" not in output.err
    assert "owner@example.test" not in output.err
    assert FIRST_PASSWORD not in output.err
    assert "sensitive internal failure" not in output.err


@pytest.mark.parametrize(
    "argv,stdin_value",
    [
        (
            [
                "--tenant",
                "local-tenant",
                "--display-name",
                "Local Tenant",
                "--email",
                "owner@example.test",
            ],
            FIRST_PASSWORD + "\n",
        ),
        (
            [
                "--tenant",
                "local-tenant",
                "--display-name",
                "Local Tenant",
                "--email",
                "owner@example.test",
                "--password-stdin",
            ],
            "short\n",
        ),
        (
            [
                "--tenant",
                "local-tenant",
                "--display-name",
                "Local Tenant",
                "--email",
                "owner@example.test",
                "--password-stdin",
            ],
            "   \n",
        ),
        (
            [
                "--tenant",
                "local-tenant",
                "--display-name",
                "Local Tenant",
                "--email",
                "owner@example.test",
                "--password",
                FIRST_PASSWORD,
            ],
            "",
        ),
    ],
)
def test_cli_rejects_missing_stdin_flag_short_blank_or_argv_password(
    monkeypatch, capsys, argv, stdin_value
):
    monkeypatch.setattr(
        bootstrap_dev,
        "Settings",
        lambda **_kwargs: SimpleNamespace(
            environment=Environment.dev,
            use_db_stores=True,
        ),
    )
    monkeypatch.setattr(bootstrap_dev.sys, "stdin", io.StringIO(stdin_value))

    assert bootstrap_dev.main(argv) == 2

    output = capsys.readouterr()
    combined = output.out + output.err
    assert "owner@example.test" not in combined
    assert FIRST_PASSWORD not in combined
