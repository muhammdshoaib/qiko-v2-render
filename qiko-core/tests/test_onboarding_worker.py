import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Agent as AgentRow
from app.db.models import AuditEventRow
from app.db.models import Passage as PassageRow
from app.db.models import PendingSignup as PendingSignupRow
from app.db.models import User as UserRow
from app.db.stores import SqlPendingSignupStore
from app.main import create_app
from app.modules.audit import registry as audit_actions
from app.modules.consent.models import COOKIES_RELEASE_ID, PRIVACY_RELEASE_ID, TERMS_RELEASE_ID
from app.modules.identity.onboarding_router import OnboardingWorkerBody
from app.modules.identity.pending_signup import make_pending_signup
from app.modules.identity.rbac import Role
from app.modules.identity.router import get_store
from app.modules.identity.store import InMemoryUserStore
from tests.helpers import auth_cookies


POLICY_ACCEPTANCE = {
    "accept_policies": True,
    "terms_release_id": TERMS_RELEASE_ID,
    "privacy_release_id": PRIVACY_RELEASE_ID,
    "cookies_release_id": COOKIES_RELEASE_ID,
}
WORKER_KNOWLEDGE = "\n\n".join([
    "Additional guidance: Explain trade-offs before making a recommendation.",
    "Common mistakes: Avoid chasing short-term performance.",
    "Frameworks: Use goals, time horizon, liquidity, and risk tolerance.",
    "Stakeholders: Balance the needs of founders and beneficiaries.",
    "Boundaries: Never promise returns or replace regulated advice.",
    "Common tasks: Compare allocations and explain portfolio risk.",
    "Example Q&A: Start risk discussions with goals and capacity.",
])
WORKER_BODY = {
    "name": "Atlas Advisor",
    "title": "Senior Wealth Strategist",
    "location": "London, UK",
    "about": "I help families make clear long-term investment decisions.",
    "tone": "professional",
    "industry": "wealth_management",
    "expertise": "Portfolio strategy, Risk analysis",
    "main_goal": "Help families make clear long-term investment decisions.",
    "knowledge": WORKER_KNOWLEDGE,
}
WORKER_CONFIG = {
    "full_name": WORKER_BODY["name"],
    "title": WORKER_BODY["title"],
    "location": WORKER_BODY["location"],
    "about": WORKER_BODY["about"],
    "tone": WORKER_BODY["tone"],
    "industry": WORKER_BODY["industry"],
    "expertise": WORKER_BODY["expertise"],
    "main_goal": WORKER_BODY["main_goal"],
}


def _audit_payload(row: dict | AuditEventRow) -> dict:
    if isinstance(row, dict):
        return row
    return {column.name: getattr(row, column.name) for column in AuditEventRow.__table__.columns}


def _created_worker_field(payload: dict, field: str):
    metadata = payload.get("event_metadata") or {}
    if field in metadata:
        return metadata[field]
    change = (payload.get("changes") or {}).get(field)
    return change.get("to") if isinstance(change, dict) else change


def _assert_sanitized_worker_created(
    row: dict | AuditEventRow,
    *,
    worker_id: str,
    worker_type: str,
    forbidden_values: list[str],
) -> None:
    payload = _audit_payload(row)
    assert payload["action"] == audit_actions.WORKER_CREATED
    assert payload["target_id"] == worker_id
    assert payload["target_type"] == "worker"
    assert _created_worker_field(payload, "type") == worker_type
    assert _created_worker_field(payload, "status") == "training"
    assert isinstance((payload.get("event_metadata") or {}).get("source"), str)
    assert (payload.get("event_metadata") or {})["source"]
    assert "name" not in (payload.get("changes") or {})
    serialized = str(payload)
    for value in forbidden_values:
        assert value not in serialized, f"worker creation audit leaked {value!r}"


def _migrated_database(tmp_path: Path) -> Path:
    database = tmp_path / "onboarding-worker.db"
    os.environ["ALEMBIC_URL"] = f"sqlite:///{database}"
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        os.environ.pop("ALEMBIC_URL", None)
    return database


def test_public_signup_materializes_one_tenant_scoped_training_worker_after_verification():
    app = create_app()
    users = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: users
    client = TestClient(app)
    email = "atlas-owner@example.test"
    password = "correct-horse-battery-staple"

    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": password,
            "name": "Morgan Owner",
            "onboarding_worker": WORKER_BODY,
            **POLICY_ACCEPTANCE,
        },
    )
    assert signup.status_code == 202, signup.text
    persisted = asyncio.run(app.state.pending_signups.get(email))
    assert persisted is not None
    assert persisted.onboarding_worker is not None
    assert persisted.onboarding_worker == {
        "id": persisted.onboarding_worker["id"],
        "name": WORKER_BODY["name"],
        "config": WORKER_CONFIG,
        "knowledge": WORKER_KNOWLEDGE,
    }

    verification = client.post(
        "/api/v1/auth/verify-email",
        json={
            "email": email,
            "code": signup.json()["verification_code"],
            "password": password,
            **POLICY_ACCEPTANCE,
        },
    )
    assert verification.status_code == 200, verification.text
    assert isinstance(verification.json()["worker_id"], str)
    worker_id = verification.json()["worker_id"]
    created_events = [
        row for row in app.state.audit.rows
        if row["action"] == audit_actions.WORKER_CREATED
    ]
    assert len(created_events) == 1
    _assert_sanitized_worker_created(
        created_events[0],
        worker_id=worker_id,
        worker_type="worker",
        forbidden_values=[email, "Morgan Owner", *[str(value) for value in WORKER_BODY.values()]],
    )

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    agents = client.get("/api/v1/agents")
    assert agents.status_code == 200, agents.text
    assert len(agents.json()) == 1
    documents = client.get(f"/api/v1/knowledge/documents?agent_id={worker_id}")
    assert documents.status_code == 200, documents.text
    assert documents.json() == [{
        "doc_id": worker_id,
        "name": "Additional guidance: Explain trade-offs before making a recommendation.",
        "chunks": 1,
        "agent_id": worker_id,
    }]
    usage = client.get("/api/v1/agents/usage")
    assert usage.status_code == 200, usage.text
    assert usage.json() == {"used_count": 1, "worker_limit": 1}
    denied = client.post("/api/v1/agents", json={"name": "Second free worker"})
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"] == "plan 'free' allows 1 worker(s)"

    user = login.json()["user"]
    worker = agents.json()[0]
    assert worker["id"] == verification.json()["worker_id"]
    assert worker["tenant"] == user["tenant"]
    assert worker["name"] == WORKER_BODY["name"]
    assert worker["status"] == "training"
    assert worker["config"] == WORKER_CONFIG


def test_normal_agent_creation_emits_only_sanitized_worker_audit(client: TestClient):
    email = "private-owner@example.test"
    private_values = {
        "account_name": "Private Account Name",
        "profile": "Private Profile Narrative",
        "location": "Private Office Location",
        "config": {"main_goal": "Private Configuration Value"},
        "knowledge": "Private Worker Knowledge",
    }
    response = client.post(
        "/api/v1/agents",
        cookies=auth_cookies("audit-tenant", "owner", email=email),
        json={"name": "Private Worker Name", "atype": "finance", **private_values},
    )
    assert response.status_code == 200, response.text

    created_events = [
        row for row in client.app.state.audit.rows
        if row["action"] == audit_actions.WORKER_CREATED
    ]
    assert len(created_events) == 1
    _assert_sanitized_worker_created(
        created_events[0],
        worker_id=response.json()["id"],
        worker_type="finance",
        forbidden_values=[
            email,
            "Private Worker Name",
            "Private Account Name",
            "Private Profile Narrative",
            "Private Office Location",
            "Private Configuration Value",
            "Private Worker Knowledge",
        ],
    )


def test_onboarding_worker_main_goal_is_bounded_at_the_signup_boundary():
    property_schema = OnboardingWorkerBody.model_json_schema()["properties"].get("main_goal")
    assert property_schema is not None
    variants = property_schema.get("anyOf", [property_schema])
    max_length = next((variant.get("maxLength") for variant in variants if "maxLength" in variant), None)
    assert isinstance(max_length, int) and max_length > 0

    app = create_app()
    app.dependency_overrides[get_store] = lambda: InMemoryUserStore()
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "overlong-goal@example.test",
            "password": "correct-horse-battery-staple",
            "name": "Morgan Owner",
            "onboarding_worker": {**WORKER_BODY, "main_goal": "x" * (max_length + 1)},
            **POLICY_ACCEPTANCE,
        },
    )

    assert response.status_code == 422, response.text
    error = next(item for item in response.json()["detail"] if item["loc"][-1] == "main_goal")
    assert error["type"] == "string_too_long"
    assert error["ctx"]["max_length"] == max_length


def test_onboarding_worker_knowledge_is_bounded_at_the_signup_boundary():
    property_schema = OnboardingWorkerBody.model_json_schema()["properties"].get("knowledge")
    assert property_schema is not None
    variants = property_schema.get("anyOf", [property_schema])
    max_length = next((variant.get("maxLength") for variant in variants if "maxLength" in variant), None)
    assert max_length == 4000

    app = create_app()
    app.dependency_overrides[get_store] = lambda: InMemoryUserStore()
    response = TestClient(app).post(
        "/api/v1/auth/signup",
        json={
            "email": "overlong-knowledge@example.test",
            "password": "correct-horse-battery-staple",
            "name": "Morgan Owner",
            "onboarding_worker": {**WORKER_BODY, "knowledge": "x" * (max_length + 1)},
            **POLICY_ACCEPTANCE,
        },
    )

    assert response.status_code == 422, response.text
    error = next(item for item in response.json()["detail"] if item["loc"][-1] == "knowledge")
    assert error["type"] == "string_too_long"
    assert error["ctx"]["max_length"] == max_length


def test_verify_signup_openapi_types_worker_id_as_optional_string():
    openapi = create_app().openapi()
    response_schema = openapi["paths"]["/api/v1/auth/verify-email"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    if "$ref" in response_schema:
        schema_name = response_schema["$ref"].rsplit("/", 1)[-1]
        response_schema = openapi["components"]["schemas"][schema_name]

    worker_id_schema = response_schema.get("properties", {}).get("worker_id")
    assert worker_id_schema is not None
    variants = worker_id_schema.get("anyOf", [worker_id_schema])
    assert any(variant.get("type") == "string" for variant in variants)
    assert "worker_id" not in response_schema.get("required", [])


def test_public_signup_without_worker_materializes_no_agents_after_verification():
    app = create_app()
    users = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: users
    client = TestClient(app)
    email = "account-only@example.test"
    password = "correct-horse-battery-staple"

    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": password,
            "name": "Account Only",
            **POLICY_ACCEPTANCE,
        },
    )
    assert signup.status_code == 202, signup.text
    verification = client.post(
        "/api/v1/auth/verify-email",
        json={
            "email": email,
            "code": signup.json()["verification_code"],
            "password": password,
            **POLICY_ACCEPTANCE,
        },
    )
    assert verification.status_code == 200, verification.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text

    agents = client.get("/api/v1/agents")
    assert agents.status_code == 200, agents.text
    assert agents.json() == []


def test_invited_signup_with_worker_is_rejected_before_any_materialization():
    app = create_app()
    users = InMemoryUserStore()
    app.dependency_overrides[get_store] = lambda: users
    client = TestClient(app)
    email = "invited-worker@example.test"

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "name": "Invited Worker",
            "invite_token": "must-not-be-consumed",
            "onboarding_worker": WORKER_BODY,
            **POLICY_ACCEPTANCE,
        },
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "invited signup cannot create an onboarding worker"
    assert asyncio.run(app.state.pending_signups.get(email)) is None
    assert asyncio.run(users.get_by_email(email)) is None
    assert asyncio.run(app.state.agents.list_all()) == []


@pytest.mark.asyncio
async def test_sql_pending_signup_round_trips_and_finalizes_named_account_with_one_worker(tmp_path: Path):
    database = _migrated_database(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    store = SqlPendingSignupStore(async_sessionmaker(engine, expire_on_commit=False))
    canonical_worker = {
        "id": "atlas-onboarding-worker",
        "name": WORKER_BODY["name"],
        "config": WORKER_CONFIG,
        "knowledge": WORKER_KNOWLEDGE,
    }
    pending, code = make_pending_signup(
        user_id="atlas-owner",
        email="atlas-sql@example.test",
        password_hash="not-login-capable",
        tenant="atlas-tenant",
        role=Role.owner,
        terms_release_id=TERMS_RELEASE_ID,
        privacy_release_id=PRIVACY_RELEASE_ID,
        cookies_release_id=COOKIES_RELEASE_ID,
        name="Morgan Owner",
        onboarding_worker=canonical_worker,
    )
    assert await store.put(pending) is True
    await engine.dispose()

    restarted_engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessionmaker = async_sessionmaker(restarted_engine, expire_on_commit=False)
    restarted_store = SqlPendingSignupStore(sessionmaker)
    restored = await restarted_store.get(pending.email)
    assert restored is not None
    assert restored.name == "Morgan Owner"
    assert restored.onboarding_worker == canonical_worker

    first = await restarted_store.finalize_signup(
        pending.email,
        code,
        "verified-password-hash",
        TERMS_RELEASE_ID,
        PRIVACY_RELEASE_ID,
        COOKIES_RELEASE_ID,
    )
    retry = await restarted_store.finalize_signup(
        pending.email,
        code,
        "verified-password-hash",
        TERMS_RELEASE_ID,
        PRIVACY_RELEASE_ID,
        COOKIES_RELEASE_ID,
    )
    assert first is not None and first[1] is True
    assert retry is not None and retry[1] is False

    async with sessionmaker() as session:
        users = (await session.scalars(select(UserRow).where(UserRow.email == pending.email))).all()
        agents = (await session.scalars(
            select(AgentRow).where(AgentRow.tenant_id == pending.tenant)
        )).all()
        passages = (await session.scalars(
            select(PassageRow).where(PassageRow.tenant_id == pending.tenant)
        )).all()
        created_events = (await session.scalars(select(AuditEventRow).where(
            AuditEventRow.action == audit_actions.WORKER_CREATED,
            AuditEventRow.target_id == canonical_worker["id"],
        ))).all()
    assert len(users) == 1
    assert users[0].name == "Morgan Owner"
    assert len(agents) == 1
    assert agents[0].id == canonical_worker["id"]
    assert agents[0].name == WORKER_BODY["name"]
    assert agents[0].status == "training"
    assert agents[0].config == WORKER_CONFIG
    assert len(passages) == 1
    assert passages[0].tenant_id == pending.tenant
    assert passages[0].agent_id == canonical_worker["id"]
    assert passages[0].doc_id == canonical_worker["id"]
    assert passages[0].text == WORKER_KNOWLEDGE
    assert passages[0].embedding == []
    assert len(created_events) == 1
    _assert_sanitized_worker_created(
        created_events[0],
        worker_id=canonical_worker["id"],
        worker_type="worker",
        forbidden_values=[pending.email, "Morgan Owner", *[str(value) for value in WORKER_BODY.values()]],
    )
    await restarted_engine.dispose()


@pytest.mark.asyncio
async def test_sql_finalization_rolls_back_account_when_onboarding_passage_insert_fails(tmp_path: Path):
    database = _migrated_database(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlPendingSignupStore(sessionmaker)
    worker_id = "atomic-onboarding-worker"
    pending, code = make_pending_signup(
        user_id="atomic-worker-owner",
        email="atomic-worker@example.test",
        password_hash="not-login-capable",
        tenant="atomic-worker-tenant",
        role=Role.owner,
        terms_release_id=TERMS_RELEASE_ID,
        privacy_release_id=PRIVACY_RELEASE_ID,
        cookies_release_id=COOKIES_RELEASE_ID,
        name="Atomic Worker Owner",
        onboarding_worker={
            "id": worker_id,
            "name": WORKER_BODY["name"],
            "config": WORKER_CONFIG,
            "knowledge": WORKER_KNOWLEDGE,
        },
    )
    assert await store.put(pending) is True

    async with sessionmaker() as session, session.begin():
        await session.execute(text(f"""
            CREATE TRIGGER reject_onboarding_passage
            BEFORE INSERT ON passages
            WHEN NEW.doc_id = '{worker_id}'
            BEGIN
                SELECT RAISE(ABORT, 'forced onboarding passage failure');
            END
        """))

    try:
        with pytest.raises(IntegrityError, match="forced onboarding passage failure"):
            await store.finalize_signup(
                pending.email,
                code,
                "verified-password-hash",
                TERMS_RELEASE_ID,
                PRIVACY_RELEASE_ID,
                COOKIES_RELEASE_ID,
            )

        async with sessionmaker() as session:
            stored_pending = await session.get(PendingSignupRow, pending.email)
            users = (await session.scalars(
                select(UserRow).where(UserRow.email == pending.email)
            )).all()
            agents = (await session.scalars(
                select(AgentRow).where(AgentRow.tenant_id == pending.tenant)
            )).all()
            passages = (await session.scalars(
                select(PassageRow).where(PassageRow.tenant_id == pending.tenant)
            )).all()
            created_events = (await session.scalars(select(AuditEventRow).where(
                AuditEventRow.tenant_id == pending.tenant,
                AuditEventRow.action == audit_actions.WORKER_CREATED,
            ))).all()
        assert stored_pending is not None and stored_pending.completed_at is None
        assert users == []
        assert agents == []
        assert passages == []
        assert created_events == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_finalization_rejects_malformed_persisted_worker_without_user_or_agent_writes(
    tmp_path: Path,
):
    database = _migrated_database(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlPendingSignupStore(sessionmaker)
    pending, code = make_pending_signup(
        user_id="malformed-worker-owner",
        email="malformed-worker@example.test",
        password_hash="not-login-capable",
        tenant="malformed-worker-tenant",
        role=Role.owner,
        terms_release_id=TERMS_RELEASE_ID,
        privacy_release_id=PRIVACY_RELEASE_ID,
        cookies_release_id=COOKIES_RELEASE_ID,
        name="Malformed Worker Owner",
        onboarding_worker={
            "id": "initially-valid-worker",
            "name": WORKER_BODY["name"],
            "config": WORKER_CONFIG,
            "knowledge": WORKER_KNOWLEDGE,
        },
    )
    assert await store.put(pending) is True

    async with sessionmaker() as session, session.begin():
        row = await session.get(PendingSignupRow, pending.email)
        assert row is not None
        row.onboarding_worker = {"id": "malformed-worker", "config": WORKER_CONFIG}

    try:
        finalized = await store.finalize_signup(
            pending.email,
            code,
            "verified-password-hash",
            TERMS_RELEASE_ID,
            PRIVACY_RELEASE_ID,
            COOKIES_RELEASE_ID,
        )
        assert finalized is None

        async with sessionmaker() as session:
            users = (
                await session.scalars(select(UserRow).where(UserRow.email == pending.email))
            ).all()
            agents = (
                await session.scalars(select(AgentRow).where(AgentRow.tenant_id == pending.tenant))
            ).all()
            passages = (
                await session.scalars(select(PassageRow).where(PassageRow.tenant_id == pending.tenant))
            ).all()
            created_events = (await session.scalars(select(AuditEventRow).where(
                AuditEventRow.tenant_id == pending.tenant,
                AuditEventRow.action == audit_actions.WORKER_CREATED,
            ))).all()
        assert users == []
        assert agents == []
        assert passages == []
        assert created_events == []
    finally:
        await engine.dispose()
