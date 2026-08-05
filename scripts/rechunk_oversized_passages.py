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
from app.db.models import Passage  # noqa: E402
from app.modules.ai.embeddings import get_embeddings  # noqa: E402
from app.modules.knowledge.chunking import chunk_text  # noqa: E402

# Anything above this was produced by the pre-fix chunker. The fixed chunker's ceiling is
# max_chars + overlap = 900, so a generous threshold avoids re-chunking rows that are merely near the
# boundary and already fine.
DEFAULT_THRESHOLD = 2_000


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
        for row in oversized:
            passage_id, tenant, agent_id, doc_id, _size = row
            async with sessionmaker() as session, session.begin():
                original = (await session.execute(
                    select(Passage).where(Passage.id == passage_id).with_for_update()
                )).scalar_one_or_none()
                if original is None:
                    continue  # already handled by a concurrent run
                parts = chunk_text(original.text, max_chars=args.max_chars, overlap=args.overlap)
                if not parts:
                    continue
                # Embedding happens inside the transaction on purpose: if a provider call fails the
                # transaction rolls back and the original passage is still there, rather than the
                # document losing a section.
                for index, part in enumerate(parts):
                    session.add(Passage(
                        id=_part_id(passage_id, index), tenant_id=tenant, agent_id=agent_id,
                        doc_id=doc_id, text=part, embedding=list(embedder.embed(part))))
                await session.delete(original)
                replaced += 1
                created += len(parts)
            print(f"  ...replaced {replaced}/{len(oversized)}, {created} chunks created", flush=True)

        print(f"done: {replaced} passage(s) replaced by {created} chunk(s)")
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
