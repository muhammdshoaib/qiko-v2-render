"""One-off ETL: legacy qiko_stage (Laravel/MySQL) -> V2 Postgres, per-user tenant isolation.

Run inside the qiko-core container (has app.modules.identity.security + psycopg):
    pip install pymysql
    MYSQL_HOST=.. MYSQL_USER=.. MYSQL_PW=.. MYSQL_DB=qiko_stage \
    PG_DSN=postgresql://qiko:pw@db:5432/qiko PREPROD_PW=preprod-test \
    python scripts/migrate_stage.py

Passwords: Laravel uses bcrypt, V2 uses PBKDF2 (incompatible), so every migrated (test) user
gets PREPROD_PW. For a real live cutover, migrate with an unusable hash + force OTP reset instead.
Knowledge (behaviors/faqs/policies/docs) needs embeddings -> handled by a separate pass.
"""
import os

import psycopg
import pymysql

from app.modules.identity.security import hash_password


def main() -> None:
    my = pymysql.connect(host=os.environ["MYSQL_HOST"], user=os.environ["MYSQL_USER"],
                         password=os.environ["MYSQL_PW"], database=os.environ["MYSQL_DB"],
                         cursorclass=pymysql.cursors.DictCursor)
    pg = psycopg.connect(os.environ["PG_DSN"], autocommit=True)
    pw_hash = hash_password(os.environ.get("PREPROD_PW", "preprod-test"))
    n = {"tenants": 0, "users": 0, "agents": 0, "conversations": 0, "messages": 0, "skipped": 0}

    def ins(sql: str, args: tuple) -> bool:
        with pg.cursor() as p:
            try:
                p.execute(sql, args)
                return True
            except Exception:
                n["skipped"] += 1
                return False

    with my.cursor() as c:
        c.execute("SELECT id, email, user_name FROM users")
        for u in c.fetchall():
            t = f"u{u['id']}"
            email = (u["email"] or f"user{u['id']}@stage.local").strip().lower()
            if ins("INSERT INTO tenants(id,name,created_at) VALUES(%s,%s,now()) ON CONFLICT (id) DO NOTHING",
                   (t, (u["user_name"] or email)[:255])):
                n["tenants"] += 1
            if ins("INSERT INTO users(id,email,password_hash,tenant_id,role,twofa_enabled,created_at) "
                   "VALUES(%s,%s,%s,%s,'owner',false,now()) ON CONFLICT (email) DO NOTHING",
                   (t, email, pw_hash, t)):
                n["users"] += 1

        agent_tenant: dict = {}
        c.execute("SELECT id, user_id, agent_name, status FROM agents")
        for a in c.fetchall():
            t = f"u{a['user_id']}"
            agent_tenant[a["id"]] = t
            status = "ready" if str(a["status"] or "").lower() in ("active", "ready", "completed", "trained", "live") else "training"
            if ins("INSERT INTO agents(id,tenant_id,name,atype,status,config,created_at) "
                   "VALUES(%s,%s,%s,'worker',%s,'{}',now()) ON CONFLICT (id) DO NOTHING",
                   (f"a{a['id']}", t, (a["agent_name"] or f"Worker {a['id']}")[:255], status)):
                n["agents"] += 1

        conv_tenant: dict = {}
        c.execute("SELECT id, created_by_agent_id FROM conversations")
        for cv in c.fetchall():
            t = agent_tenant.get(cv["created_by_agent_id"])
            if not t:
                n["skipped"] += 1
                continue
            conv_tenant[cv["id"]] = t
            if ins("INSERT INTO conversations(id,tenant_id,user_id,agent_id,created_at) "
                   "VALUES(%s,%s,%s,%s,now()) ON CONFLICT (id) DO NOTHING",
                   (f"c{cv['id']}", t, t, f"a{cv['created_by_agent_id']}")):
                n["conversations"] += 1

        c.execute("SELECT conversation_id, sender_agent_id, message FROM messages ORDER BY id")
        for m in c.fetchall():
            t = conv_tenant.get(m["conversation_id"])
            if not t:
                n["skipped"] += 1
                continue
            role = "assistant" if m["sender_agent_id"] else "user"
            if ins("INSERT INTO messages(conversation_id,tenant_id,role,body,created_at) "
                   "VALUES(%s,%s,%s,%s,now())", (f"c{m['conversation_id']}", t, role, m["message"] or "")):
                n["messages"] += 1

    print("MIGRATION_DONE", n)


if __name__ == "__main__":
    main()
