"""One-off ETL: import a pre-extracted knowledge corpus (JSONL: {doc_id/source, text, ...}) into
a tenant's knowledge base via the app's own KnowledgeService (same embeddings/store config as the
running app -- no HTTP hop, no duplicate logic).

Usage (inside the qiko-core container):
    python scripts/import_kb_jsonl.py --tenant idg --file /tmp/kb_corpus.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Iterator


def parse_jsonl_docs(path: str) -> Iterator[tuple[str, str]]:
    """Yield (doc_id, text) pairs from a corpus JSONL, skipping blank/empty-text rows."""
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = row.get("text", "")
            if not text.strip():
                continue
            doc_id = row.get("filename") or row.get("source") or f"doc-{i}"
            yield doc_id, text


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    from app.core.db import build_engine, build_sessionmaker
    from app.db.stores import SqlVectorStore
    from app.modules.knowledge.service import KnowledgeService

    engine = build_engine()
    sm = build_sessionmaker(engine)
    knowledge = KnowledgeService(store=SqlVectorStore(sm))

    n_docs = 0
    n_chunks = 0
    for doc_id, text in parse_jsonl_docs(args.file):
        n_chunks += await knowledge.ingest(args.tenant, doc_id, text)
        n_docs += 1
    print(f"IMPORT_DONE tenant={args.tenant} docs={n_docs} chunks={n_chunks}")


if __name__ == "__main__":
    asyncio.run(main())
