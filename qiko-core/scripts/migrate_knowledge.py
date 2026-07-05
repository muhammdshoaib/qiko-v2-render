"""One-off ETL, part 2: legacy qiko_stage behaviors/faqs/policies/websites -> V2 knowledge base
(real embeddings via the app's own KnowledgeService/SqlVectorStore -- same pipeline as chat RAG).

This is the "separate pass" migrate_stage.py deferred (its docstring: "Knowledge (behaviors/faqs/
policies/docs) needs embeddings -> handled by a separate pass"). Tenant mapping matches
migrate_stage.py exactly: legacy agents.user_id -> V2 tenant "u{user_id}".

`agent_documents` (uploaded files) is NOT covered here -- it needs the legacy file storage (S3 or
local uploads dir) to fetch + parse each file, which is a bigger, separate piece of work.

Run inside the qiko-core container:
    pip install pymysql
    MYSQL_HOST=.. MYSQL_USER=.. MYSQL_PW=.. MYSQL_DB=qiko_stage python scripts/migrate_knowledge.py
"""
from __future__ import annotations

import asyncio
import os


def behavior_text(row: dict) -> str:
    return f"{row['type']}: {row['title']}\n{row['description'] or ''}".strip()


def faq_text(row: dict) -> str:
    return f"Q: {row['question']}\nA: {row['answer'] or ''}".strip()


def policy_text(row: dict) -> str:
    return f"Policy — {row['name']}:\n{row['details'] or ''}".strip()


def website_text(row: dict) -> str:
    return f"Website reference — {row['name']}: {row['url']}".strip()


async def main() -> None:
    import pymysql

    from app.core.db import build_engine, build_sessionmaker
    from app.db.stores import SqlVectorStore
    from app.modules.knowledge.service import KnowledgeService

    my = pymysql.connect(host=os.environ["MYSQL_HOST"], user=os.environ["MYSQL_USER"],
                         password=os.environ["MYSQL_PW"], database=os.environ["MYSQL_DB"],
                         cursorclass=pymysql.cursors.DictCursor)
    engine = build_engine()
    sm = build_sessionmaker(engine)
    knowledge = KnowledgeService(store=SqlVectorStore(sm))

    with my.cursor() as c:
        c.execute("SELECT id, user_id FROM agents")
        agent_tenant = {a["id"]: f"u{a['user_id']}" for a in c.fetchall()}

    counts = {"behaviors": 0, "faqs": 0, "policies": 0, "websites": 0, "chunks": 0, "skipped": 0}

    async def ingest_rows(table: str, sql: str, doc_prefix: str, to_text) -> None:
        with my.cursor() as c:
            c.execute(sql)
            for row in c.fetchall():
                tenant = agent_tenant.get(row["agent_id"])
                if not tenant:
                    counts["skipped"] += 1
                    continue
                text = to_text(row)
                if not text.strip():
                    counts["skipped"] += 1
                    continue
                chunks = await knowledge.ingest(tenant, f"{doc_prefix}{row['id']}", text)
                counts[table] += 1
                counts["chunks"] += chunks

    await ingest_rows("behaviors", "SELECT id, agent_id, type, title, description FROM behaviors",
                      "behavior-", behavior_text)
    await ingest_rows("faqs", "SELECT id, agent_id, question, answer FROM faqs WHERE deleted_at IS NULL",
                      "faq-", faq_text)
    await ingest_rows("policies", "SELECT id, agent_id, name, details FROM policies WHERE deleted_at IS NULL",
                      "policy-", policy_text)
    await ingest_rows("websites", "SELECT id, agent_id, name, url FROM websites WHERE deleted_at IS NULL",
                      "website-", website_text)

    print("KNOWLEDGE_MIGRATION_DONE", counts)


if __name__ == "__main__":
    asyncio.run(main())
