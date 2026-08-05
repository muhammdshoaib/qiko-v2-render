"""Recompute stored passage embeddings with the CURRENTLY configured provider.

Why this exists
---------------
`passages.embedding` holds vectors produced by whatever `EMBEDDINGS_PROVIDER` was active when the
document was ingested. Vectors from different providers are not comparable: `LocalEmbeddings` is a
SHA-256 bag-of-words hash into buckets, while Titan is a real semantic model. Switching the provider
without recomputing leaves the corpus in the worst possible state, because retrieval keeps working
and silently returns near-random passages.

`passages.text` is stored alongside the vector, so a rebuild needs no re-ingestion of source files.

Usage (from the repo root, inside the qiko-core container so the settings and credentials resolve):

    # always dry-run first: reports what WOULD change, touches nothing
    python scripts/reembed_passages.py

    # rebuild everything
    python scripts/reembed_passages.py --apply

    # one tenant only, smaller batches
    python scripts/reembed_passages.py --apply --tenant idg --batch-size 100

Safe to re-run: it is idempotent (the same text and provider produce the same vector) and it only
ever writes the `embedding` column, never the text, ids or ownership.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qiko-core"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import Passage  # noqa: E402
from app.modules.ai.embeddings import get_embeddings  # noqa: E402

# Titan enforces TWO independent limits, and the character one is not the binding constraint:
#   - "expected maxLength: 50000"          -> characters
#   - "Max input tokens: 8192"             -> tokens, which a 40k-char window already exceeded (8455)
# Token density varies a lot by content (prose ~4 chars/token, tables and code closer to 2), so a
# fixed window cannot be proven safe from the character count alone. Use a conservative window AND
# halve it on a token-limit rejection, so the tool self-corrects instead of aborting a rebuild
# halfway through.
TITAN_MAX_CHARS = 50_000
TITAN_MAX_TOKENS = 8_192
WINDOW_CHARS = 16_000  # ~4k tokens at 4 chars/token, ~8k in the worst realistic density
MIN_WINDOW_CHARS = 1_000


def _embed_window(embedder, window: str) -> list[float]:
    """Embed one window, halving it on a token-limit rejection until it fits."""
    size = len(window)
    while True:
        try:
            return list(embedder.embed(window[:size]))
        except Exception as error:  # noqa: BLE001 - provider SDKs raise their own error types
            message = str(error)
            too_long = "Too many input tokens" in message or "maxLength" in message
            if not too_long or size <= MIN_WINDOW_CHARS:
                raise
            size = max(MIN_WINDOW_CHARS, size // 2)
            print(f"    window rejected as too long, retrying at {size} chars", flush=True)


def embed_text(embedder, text: str) -> list[float]:
    if len(text) <= WINDOW_CHARS:
        return _embed_window(embedder, text)
    windows = [text[i:i + WINDOW_CHARS] for i in range(0, len(text), WINDOW_CHARS)]
    vectors = [_embed_window(embedder, window) for window in windows]
    return [sum(values) / len(values) for values in zip(*vectors, strict=True)]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="write the new vectors. Without it the script only reports (dry run).")
    parser.add_argument("--tenant", default=None, help="restrict to one tenant id.")
    parser.add_argument("--batch-size", type=int, default=200,
                        help="rows per transaction (default 200).")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    embedder = get_embeddings()
    provider = settings.embeddings_provider
    print(f"provider={provider} dim={settings.embeddings_dim} "
          f"tenant={args.tenant or 'ALL'} mode={'APPLY' if args.apply else 'DRY RUN'}")

    engine = create_async_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    def scoped(statement):
        return statement.where(Passage.tenant_id == args.tenant) if args.tenant else statement

    async with sessionmaker() as session:
        total = (await session.execute(scoped(select(func.count()).select_from(Passage)))).scalar_one()
    async with sessionmaker() as session:
        oversized = (await session.execute(scoped(
            select(func.count()).select_from(Passage).where(func.length(Passage.text) > WINDOW_CHARS)
        ))).scalar_one()
    print(f"passages in scope: {total} ({oversized} need window mean-pooling above "
          f"{WINDOW_CHARS} chars; Titan caps input at {TITAN_MAX_CHARS} chars AND "
          f"{TITAN_MAX_TOKENS} tokens)")
    if total == 0:
        await engine.dispose()
        return 0

    if not args.apply:
        async with sessionmaker() as session:
            sample = (await session.execute(scoped(select(Passage).limit(3)))).scalars().all()
        for passage in sample:
            current = passage.embedding or []
            rebuilt = embed_text(embedder, passage.text)
            changed = "CHANGED" if list(current) != list(rebuilt) else "same"
            pooled = " (mean-pooled over windows)" if len(passage.text) > WINDOW_CHARS else ""
            print(f"  {passage.tenant_id}/{passage.doc_id}/{passage.id[:12]}: chars={len(passage.text)} "
                  f"stored_dim={len(current)} new_dim={len(rebuilt)} -> {changed}{pooled}")
        print(f"\nDRY RUN: nothing written. Re-run with --apply to rebuild {total} vector(s).")
        await engine.dispose()
        return 0

    processed = 0
    rewritten = 0
    offset = 0
    while True:
        async with sessionmaker.begin() as session:
            rows = (await session.execute(
                scoped(select(Passage).order_by(Passage.id).offset(offset).limit(args.batch_size))
            )).scalars().all()
            if not rows:
                break
            for passage in rows:
                rebuilt = embed_text(embedder, passage.text)
                if list(passage.embedding or []) != list(rebuilt):
                    passage.embedding = rebuilt
                    rewritten += 1
                processed += 1
        offset += args.batch_size
        print(f"  ...{processed}/{total} processed, {rewritten} rewritten", flush=True)

    print(f"done: {processed} processed, {rewritten} rewritten with provider={provider}")
    await engine.dispose()
    return 0


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
