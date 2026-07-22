"""The admin Customers console (SqlCustomerDirectory) derived from the real tenants.

Instead of a parallel directory that nothing populates (so the admin page was always empty), the
directory aggregates the actual tenants/users/agents/subscriptions/invoices. Run on SQLite, the
sync analogue of the async DB-backed store tests."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Agent as AgentRow
from app.db.models import Tenant as TenantRow
from app.db.models import User as UserRow
from app.db.sync_stores import SqlCustomerDirectory, SqlInvoiceStore, SqlSubscriptionStore
from app.modules.billing.subscriptions import Subscription
from app.modules.billing.webhook import Invoice


def _sessionmaker(path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _seed(sm):
    with sm() as s, s.begin():
        s.add_all([
            TenantRow(id="acme", name="Acme Ltd"),
            TenantRow(id="globex", name="Globex"),
            UserRow(id="u1", email="owner@acme.com", password_hash="x", tenant_id="acme", role="owner"),
            UserRow(id="u2", email="staff@acme.com", password_hash="x", tenant_id="acme", role="viewer"),
            UserRow(id="u3", email="boss@globex.com", password_hash="x", tenant_id="globex", role="owner"),
            AgentRow(id="a1", tenant_id="acme", name="Worker A"),
            AgentRow(id="a2", tenant_id="acme", name="Worker B"),
        ])
    # acme is on the Premium plan, linked to a Stripe customer with one paid invoice.
    SqlSubscriptionStore(sm).put(Subscription("acme", "pro", "active"))
    SqlSubscriptionStore(sm).set_customer("acme", "cus_acme")
    SqlInvoiceStore(sm).upsert(Invoice("in_1", "cus_acme", 10000, "paid"))
    SqlInvoiceStore(sm).upsert(Invoice("in_2", "cus_acme", 500, "open"))  # unpaid, not counted


def test_directory_reflects_real_tenants(tmp_path):
    sm = _sessionmaker(tmp_path / "cust.db")
    _seed(sm)
    directory = SqlCustomerDirectory(sm)

    res = directory.list()
    assert res["total"] == 2
    assert {r.user_id for r in res["items"]} == {"acme", "globex"}
    # highest earnings first (acme has a paid invoice, globex none)
    assert res["items"][0].user_id == "acme"

    acme = next(r for r in res["items"] if r.user_id == "acme")
    assert acme.email == "owner@acme.com"      # the owner's email is the shown identity
    assert acme.plan == "pro"                   # from its real subscription
    assert acme.agents == 2                      # worker count
    assert acme.earnings_cents == 10000          # only the paid invoice

    globex = next(r for r in res["items"] if r.user_id == "globex")
    assert globex.plan == "free" and globex.agents == 0 and globex.earnings_cents == 0


def test_search_and_plan_filter(tmp_path):
    sm = _sessionmaker(tmp_path / "filter.db")
    _seed(sm)
    directory = SqlCustomerDirectory(sm)
    assert {r.user_id for r in directory.list(plan="pro")["items"]} == {"acme"}
    assert directory.list(search="globex")["total"] == 1
    assert directory.list(search="owner@acme")["items"][0].user_id == "acme"


def test_details_studio_and_soft_delete(tmp_path):
    sm = _sessionmaker(tmp_path / "flags.db")
    _seed(sm)
    directory = SqlCustomerDirectory(sm)

    assert directory.details("acme").is_studio is False
    assert directory.set_studio("acme", True).is_studio is True
    assert directory.details("acme").is_studio is True    # persisted

    deleted = directory.soft_delete("globex")
    assert deleted.deleted is True and "anonymized.invalid" in deleted.email
    assert directory.details("globex") is None             # excluded once deleted
    assert {r.user_id for r in directory.list()["items"]} == {"acme"}

    # Studio/soft-delete on an unknown tenant -> KeyError (the admin router turns this into a 404).
    with pytest.raises(KeyError):
        directory.set_studio("nope", True)
    with pytest.raises(KeyError):
        directory.soft_delete("nope")


def test_flags_survive_a_fresh_directory_instance(tmp_path):
    path = tmp_path / "persist.db"
    sm = _sessionmaker(path)
    _seed(sm)
    SqlCustomerDirectory(sm).set_studio("acme", True)
    # A fresh directory on a new engine to the same DB still sees the flag.
    sm2 = sessionmaker(create_engine(f"sqlite:///{path}"), expire_on_commit=False)
    assert SqlCustomerDirectory(sm2).details("acme").is_studio is True
