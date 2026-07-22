import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Agent, Tenant, User
from app.modules.identity.security import verify_password
from scripts import provision_tenant


INITIAL_PASSWORD = "correct-horse-battery-staple"


def _database(tmp_path, monkeypatch, *, environment="dev"):
    path = tmp_path / "provisioning.db"
    sync_url = f"sqlite:///{path}"
    engine = create_engine(sync_url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{path}")
    monkeypatch.setenv("ENVIRONMENT", environment)
    return engine


def _manifest(tmp_path, *, tenant="example-tenant", users=None, agents=None, extra=None):
    data = {
        "tenant": {"slug": tenant, "display_name": "Example Tenant"},
        "users": users if users is not None else [{"email": "owner@example.com", "role": "owner"}],
        "agents": agents if agents is not None else [{
            "id": "example-sales-worker",
            "name": "Example Sales Worker",
            "atype": "sales_intelligence",
            "status": "ready",
            "config": {"archived": True, "scan_interval_minutes": 15},
        }],
    }
    if extra:
        data.update(extra)
    path = tmp_path / "tenant-manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _invoke(path, *args):
    return provision_tenant.main(["--manifest", str(path), *args])


def _counts(engine):
    with Session(engine) as session:
        return (
            session.scalar(select(func.count()).select_from(Tenant)),
            session.scalar(select(func.count()).select_from(User)),
            session.scalar(select(func.count()).select_from(Agent)),
        )


def test_manifest_inside_git_repository_is_rejected(monkeypatch, capsys):
    repository_root = Path(provision_tenant.__file__).resolve().parents[2]
    path = repository_root / "operator-test-manifest.json"
    path.write_text("{}", encoding="utf-8")
    try:
        assert _invoke(path) == 2
        assert "outside the repository" in capsys.readouterr().err
    finally:
        path.unlink()


def test_dry_run_reports_plan_without_writing(tmp_path, monkeypatch, capsys):
    engine = _database(tmp_path, monkeypatch)
    path = _manifest(tmp_path)

    assert _invoke(path) == 0

    assert _counts(engine) == (0, 0, 0)
    output = capsys.readouterr().out
    assert "DRY_RUN tenant=example-tenant changes=3" in output
    assert "tenants_created=1" in output
    assert "users_created=1" in output
    assert "agents_created=1" in output


def test_first_apply_creates_tenant_users_and_agents(tmp_path, monkeypatch, capsys):
    engine = _database(tmp_path, monkeypatch)
    path = _manifest(
        tmp_path,
        users=[
            {"email": "owner@example.com", "role": "owner"},
            {"email": "editor@example.com", "role": "editor"},
        ],
    )

    assert _invoke(path, "--apply") == 0

    with Session(engine) as session:
        tenant = session.get(Tenant, "example-tenant")
        users = session.scalars(select(User).order_by(User.email)).all()
        agent = session.get(Agent, "example-sales-worker")
        assert tenant.name == "Example Tenant"
        assert [(user.email, user.role, user.tenant_id) for user in users] == [
            ("editor@example.com", "editor", "example-tenant"),
            ("owner@example.com", "owner", "example-tenant"),
        ]
        assert len({user.password_hash for user in users}) == 2
        assert all(not verify_password(INITIAL_PASSWORD, user.password_hash) for user in users)
        assert (agent.tenant_id, agent.atype, agent.status) == (
            "example-tenant",
            "sales_intelligence",
            "ready",
        )
        assert agent.config == {"archived": True, "scan_interval_minutes": 15}
    assert "APPLIED tenant=example-tenant changes=4" in capsys.readouterr().out


def test_second_apply_is_a_no_op(tmp_path, monkeypatch, capsys):
    engine = _database(tmp_path, monkeypatch)
    path = _manifest(tmp_path)
    assert _invoke(path, "--apply") == 0
    capsys.readouterr()

    assert _invoke(path, "--apply") == 0

    assert _counts(engine) == (1, 1, 1)
    assert "NO_CHANGES tenant=example-tenant changes=0" in capsys.readouterr().out


def test_apply_aligns_role_and_agent_fields_while_preserving_unrelated_config_and_password(
    tmp_path, monkeypatch
):
    engine = _database(tmp_path, monkeypatch)
    original_hash = "existing-password-hash"
    with Session(engine) as session, session.begin():
        session.add(Tenant(id="example-tenant", name="Old Name"))
        session.add(User(
            id="existing-user",
            email="owner@example.com",
            password_hash=original_hash,
            tenant_id="example-tenant",
            role="viewer",
        ))
        session.add(Agent(
            id="example-sales-worker",
            tenant_id="example-tenant",
            name="Old Worker Name",
            atype="worker",
            status="training",
            config={"archived": False, "unrelated": "keep", "nested": {"keep": True}},
        ))
    path = _manifest(tmp_path)

    assert _invoke(path, "--apply") == 0

    with Session(engine) as session:
        tenant = session.get(Tenant, "example-tenant")
        user = session.get(User, "existing-user")
        agent = session.get(Agent, "example-sales-worker")
        assert tenant.name == "Example Tenant"
        assert user.role == "owner"
        assert user.password_hash == original_hash
        assert (agent.name, agent.atype, agent.status) == (
            "Example Sales Worker",
            "sales_intelligence",
            "ready",
        )
        assert agent.config == {
            "archived": True,
            "unrelated": "keep",
            "nested": {"keep": True},
            "scan_interval_minutes": 15,
        }


def test_cross_tenant_email_collision_fails_closed_before_writes(tmp_path, monkeypatch, capsys):
    engine = _database(tmp_path, monkeypatch)
    with Session(engine) as session, session.begin():
        session.add(Tenant(id="other-tenant", name="Other Tenant"))
        session.add(User(
            id="other-user",
            email="owner@example.com",
            password_hash="unchanged",
            tenant_id="other-tenant",
            role="owner",
        ))
    path = _manifest(tmp_path)

    assert _invoke(path, "--apply") == 2

    assert _counts(engine) == (1, 1, 0)
    with Session(engine) as session:
        assert session.get(Tenant, "example-tenant") is None
        assert session.get(User, "other-user").password_hash == "unchanged"
    output = capsys.readouterr()
    assert "belongs to another tenant" in output.err
    assert "owner@example.com" not in output.err


def test_new_users_receive_unique_unrecoverable_credentials_without_shared_password(
    tmp_path, monkeypatch
):
    engine = _database(tmp_path, monkeypatch)
    path = _manifest(tmp_path, users=[
        {"email": "first@example.com", "role": "owner"},
        {"email": "second@example.com", "role": "editor"},
    ])

    assert _invoke(path, "--apply") == 0

    with Session(engine) as session:
        users = session.scalars(select(User).order_by(User.email)).all()
        assert len({user.password_hash for user in users}) == 2
        assert all(not verify_password(INITIAL_PASSWORD, user.password_hash) for user in users)


def test_existing_password_is_only_reset_with_explicit_flag(tmp_path, monkeypatch):
    engine = _database(tmp_path, monkeypatch)
    with Session(engine) as session, session.begin():
        session.add(Tenant(id="example-tenant", name="Example Tenant"))
        session.add(User(
            id="existing-user",
            email="owner@example.com",
            password_hash="old-password-hash",
            tenant_id="example-tenant",
            role="owner",
        ))
    path = _manifest(tmp_path, agents=[])

    assert _invoke(path, "--apply") == 0
    with Session(engine) as session:
        assert session.get(User, "existing-user").password_hash == "old-password-hash"

    assert _invoke(path, "--apply", "--reset-existing-passwords") == 0
    with Session(engine) as session:
        password_hash = session.get(User, "existing-user").password_hash
        assert password_hash != "old-password-hash"
        assert not verify_password(INITIAL_PASSWORD, password_hash)


def test_live_apply_requires_exact_non_interactive_tenant_confirmation(tmp_path, monkeypatch, capsys):
    engine = _database(tmp_path, monkeypatch, environment="live")
    path = _manifest(tmp_path)

    assert _invoke(path, "--apply") == 2
    assert _invoke(path, "--apply", "--confirm-tenant", "wrong-tenant") == 2
    assert _counts(engine) == (0, 0, 0)

    assert _invoke(path, "--apply", "--confirm-tenant", "example-tenant") == 0
    assert _counts(engine) == (1, 1, 1)
    output = capsys.readouterr()
    assert "live writes require --confirm-tenant" in output.err


@pytest.mark.parametrize(
    "users,agents,extra",
    [
        ([{"email": "owner@example.com", "role": "superuser"}], [], None),
        ([], [{
            "id": "bad-agent",
            "name": "Bad Agent",
            "atype": "untrusted_type",
            "status": "ready",
            "config": {},
        }], None),
        ([], [], {"password": "must-not-be-accepted"}),
    ],
)
def test_invalid_manifest_role_atype_or_extra_field_is_rejected(
    tmp_path, monkeypatch, users, agents, extra
):
    engine = _database(tmp_path, monkeypatch)
    path = _manifest(tmp_path, users=users, agents=agents, extra=extra)

    assert _invoke(path, "--apply") == 2

    assert _counts(engine) == (0, 0, 0)


def test_password_hash_and_user_email_never_appear_in_output(tmp_path, monkeypatch, capsys):
    _database(tmp_path, monkeypatch)
    path = _manifest(tmp_path)

    assert _invoke(path) == 0
    assert _invoke(path, "--apply") == 0

    output = capsys.readouterr()
    combined = output.out + output.err
    assert "pbkdf2_sha256" not in combined
    assert "owner@example.com" not in combined
