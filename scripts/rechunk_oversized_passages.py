"""Split passages that were stored as one oversized chunk, in place.

Why this is possible without asking anyone to re-upload anything
---------------------------------------------------------------
`passages.text` holds the ALREADY EXTRACTED text, so the source document is not needed. The chunker bug
(a paragraph larger than the window was emitted whole, so a PDF with no blank lines became one chunk)
left six passages between 50k and 149,579 characters. Everything needed to split them correctly is in
the row.

Why per passage rather than per document
---------------------------------------
Reconstructing a document from its chunks is not reliable: chunks carry a deliberate overlap, so
concatenating them duplicates text at every boundary, and nothing records the original order beyond an
id hash. Re-chunking each oversized passage on its own is exact: the text inside it is split properly,
and its boundaries with neighbouring passages are left exactly as they were, since those already carry
their own overlap.

Safety properties
-----------------
- Dry run by default. `--apply` writes.
- One transaction per passage, so an interruption cannot leave a document half re-chunked: either a
  passage is replaced by its parts or it is untouched.
- New ids are derived from the original id, so a re-run is idempotent and the ids stay deterministic.
- Never touches `tenant_id`, `agent_id` or `doc_id`, so citations, which key on `doc_id`, are unchanged.
- The original row is deleted only after its replacements are added in the same transaction.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qiko-core"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.tenancy import reset_tenant, set_tenant  # noqa: E402
from app.db.models import Passage  # noqa: E402
from app.modules.ai import usage  # noqa: E402
from app.modules.ai.embeddings import get_embeddings  # noqa: E402
from app.modules.knowledge.chunking import chunk_text  # noqa: E402

# 16,000 characters, and the number is not arbitrary. It is the point at which the re-embed tool must
# start mean-pooling, because Titan refuses input above 8,192 tokens. So above this line a passage is
# degraded twice over: its citation points at a whole document AND its vector is an average of windows
# rather than a real embedding of the text.
#
# Below the line a passage is merely suboptimal. The live distribution makes the trade concrete:
# p50=670, p90=2,109, p99=19,985, max=149,579. A 2,000 threshold would rewrite 195 passages, 10.4% of
# the corpus, most of them only 2.6x the window. That is a retrieval-semantics change at scale for
# little gain: BM25's idf and avgdl are corpus-wide, so re-chunking a tenth of the corpus shifts the
# ranking of documents nobody touched. A 16,000 threshold rewrites 28 passages, 1.5%, and those are the
# ones whose vectors are actually wrong.
DEFAULT_THRESHOLD = 16_000


def _part_id(original_id: str, index: int) -> str:
    """Deterministic child id, so a second run produces the same ids and changes nothing."""
    return hashlib.sha1(f"rechunk:{original_id}:{index}".encode()).hexdigest()[:16]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Split oversized passages in place.")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--tenant", default=None, help="limit to one tenant")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"re-chunk passages longer than this (default {DEFAULT_THRESHOLD})")
    parser.add_argument("--max-chars", type=int, default=800, help="chunk window")
    parser.add_argument("--overlap", type=int, default=100, help="chunk overlap")
    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    embedder = get_embeddings()
    engine = create_async_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    def scoped(query):
        return query.where(Passage.tenant_id == args.tenant) if args.tenant else query

    try:
        async with sessionmaker() as session:
            oversized = (await session.execute(scoped(
                select(Passage.id, Passage.tenant_id, Passage.agent_id, Passage.doc_id,
                       func.length(Passage.text))
                .where(func.length(Passage.text) > args.threshold)
                .order_by(func.length(Passage.text).desc())
            ))).all()

        print(f"provider={settings.embeddings_provider} tenant={args.tenant or 'ALL'} "
              f"threshold={args.threshold} window={args.max_chars}/{args.overlap} "
              f"mode={'APPLY' if args.apply else 'DRY RUN'}")
        if not oversized:
            print("nothing above the threshold; nothing to do")
            return 0

        print(f"oversized passages: {len(oversized)}")
        planned = 0
        for row in oversized:
            passage_id, tenant, _agent, doc_id, size = row
            async with sessionmaker() as session:
                text = (await session.execute(
                    select(Passage.text).where(Passage.id == passage_id))).scalar_one()
            parts = chunk_text(text, max_chars=args.max_chars, overlap=args.overlap)
            planned += len(parts)
            print(f"  {tenant}/{doc_id[:44]}: {size} chars -> {len(parts)} chunks "
                  f"(max {max(len(p) for p in parts)})")

        if not args.apply:
            print(f"\nDRY RUN: nothing written. --apply would replace {len(oversized)} passage(s) "
                  f"with {planned} chunk(s).")
            return 0

        replaced = 0
        created = 0
        store = None
        try:
            from app.db.stores import SqlUsageStore

            store = SqlUsageStore(sessionmaker)
        except Exception:  # noqa: BLE001 - accounting must never stop the migration
            store = None

        async def replace_one(passage_id: str, tenant: str, agent_id, doc_id: str) -> int:
            """Replace one oversized passage with its parts. Returns the number of parts written.

            A proper context manager rather than manual enter/exit: if the transaction raises, the
            tenant binding and the usage scope must still be unwound, otherwise the next passage would
            be attributed to the previous tenant.
            """
            async with sessionmaker() as session, session.begin():
                original = (await session.execute(
                    select(Passage).where(Passage.id == passage_id).with_for_update()
                )).scalar_one_or_none()
                if original is None:
                    return 0  # already handled by a concurrent run
                parts = chunk_text(original.text, max_chars=args.max_chars, overlap=args.overlap)
                if not parts:
                    return 0
                # Embedding happens inside the transaction on purpose: if a provider call fails the
                # transaction rolls back and the original passage is still there, rather than the
                # document losing a section.
                for index, part in enumerate(parts):
                    session.add(Passage(
                        id=_part_id(passage_id, index), tenant_id=tenant, agent_id=agent_id,
                        doc_id=doc_id, text=part, embedding=list(embedder.embed(part))))
                await session.delete(original)
                return len(parts)

        for row in oversized:
            passage_id, tenant, agent_id, doc_id, _size = row
            # Attribute the embedding spend to the tenant whose passage this is. Without a scope the
            # instrumentation warned "outside a scope" once per call and the spend, which is real
            # Bedrock money and the largest single burst this platform makes, went unrecorded.
            tenant_token = set_tenant(tenant)
            try:
                with usage.scope() as events:
                    parts_written = await replace_one(passage_id, tenant, agent_id, doc_id)
                    await usage.flush(store, events)
            finally:
                reset_tenant(tenant_token)
            if parts_written:
                replaced += 1
                created += parts_written
            print(f"  ...replaced {replaced}/{len(oversized)}, {created} chunks created", flush=True)

        print(f"done: {replaced} passage(s) replaced by {created} chunk(s)")
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
