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
    assert {"tenants", "users", "verified_answers", "passages"} <= tables
