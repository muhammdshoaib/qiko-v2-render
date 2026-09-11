import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_every_revision_id_fits_the_real_alembic_version_column():
    # alembic_version.version_num is varchar(32) on Postgres (alembic's own default schema,
    # never widened by this codebase). SQLite (used by every other test in this file) does not
    # enforce VARCHAR length, so a too-long revision id passes every local/CI migration test and
    # only fails against the real production database, with a StringDataRightTruncation error
    # from `alembic upgrade head` - which is exactly what happened with the original
    # "0051_opportunity_pipeline_verdict" (33 chars) before it was renamed. This test makes that
    # class of bug fail locally instead of on a live deploy.
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    too_long = {rev.revision: len(rev.revision) for rev in scripts.walk_revisions()
                if len(rev.revision) > 32}
    assert too_long == {}


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


def test_passage_embedding_vector_migration_is_a_noop_on_sqlite(tmp_path):
    db = tmp_path / "vec.db"
    os.environ["ALEMBIC_URL"] = f"sqlite:///{db}"
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
    finally:
        os.environ.pop("ALEMBIC_URL", None)

    con = sqlite3.connect(db)
    columns = {row[1] for row in con.execute("pragma table_info(passages)")}
    con.close()
    # SQLite never gets embedding_vec - the migration's dialect guard must skip it entirely,
    # not fail, not add a differently-typed column.
    assert "embedding_vec" not in columns


def test_opportunity_pipeline_verdict_migration_adds_nullable_columns(tmp_path):
    db = tmp_path / "verdict.db"
    os.environ["ALEMBIC_URL"] = f"sqlite:///{db}"
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
    finally:
        os.environ.pop("ALEMBIC_URL", None)

    con = sqlite3.connect(db)
    columns = {row[1] for row in con.execute("pragma table_info(sales_intel_opportunities)")}
    con.close()
    assert "pipeline_verdict" in columns
    assert "pipeline_run_id" in columns
