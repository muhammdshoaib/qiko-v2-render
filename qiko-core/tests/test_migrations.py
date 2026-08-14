import os
import sqlite3

from alembic import command
from alembic.config import Config


def test_alembic_upgrade_head_creates_schema(tmp_path):
    db = tmp_path / "mig.db"
    os.environ["ALEMBIC_URL"] = f"sqlite:///{db}"
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
    finally:
        os.environ.pop("ALEMBIC_URL", None)

    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    assert {"tenants", "users", "verified_answers", "passages",
            "password_reset_otps", "pending_team_invites"} <= tables


def test_conversation_crm_eligibility_migration_backfills_existing_rows(tmp_path):
    db = tmp_path / "crm-origin.db"
    os.environ["ALEMBIC_URL"] = f"sqlite:///{db}"
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0039_audit_append_only")
        con = sqlite3.connect(db)
        con.execute("insert into conversations (id, tenant_id, user_id, agent_id) values (?, ?, ?, ?)",
                    ("internal", "acme", "public", "a1"))
        con.execute("insert into conversations (id, tenant_id, user_id, agent_id) values (?, ?, ?, ?)",
                    ("visitor", "acme", "guest@public", "a1"))
        con.commit()
        con.close()
        command.upgrade(cfg, "head")
    finally:
        os.environ.pop("ALEMBIC_URL", None)

    con = sqlite3.connect(db)
    values = dict(con.execute("select id, crm_eligible from conversations"))
    columns = {row[1]: row[2] for row in con.execute("pragma table_info(conversations)")}
    con.close()
    assert values == {"internal": 0, "visitor": 1}
    assert columns["user_id"] == "VARCHAR(320)"
