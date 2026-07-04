"""Hybrid retrieval: dense (cosine over embeddings) + sparse (BM25 over terms), fused with
Reciprocal Rank Fusion. Combining both beats either alone, as validated in the IDG worker."""
from __future__ import annotations

import math
import re

_WORD = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def bm25_scores(query: str, docs: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    """BM25 Okapi score of the query against each document."""
    doc_terms = [_terms(d) for d in docs]
    n = len(docs)
    if n == 0:
        return []
    avgdl = sum(len(dt) for dt in doc_terms) / n or 1.0
    # document frequency per query term
    q_terms = set(_terms(query))
    df = {t: sum(1 for dt in doc_terms if t in dt) for t in q_terms}
    scores = [0.0] * n
    for i, dt in enumerate(doc_terms):
        dl = len(dt) or 1
        for t in q_terms:
            if df.get(t, 0) == 0:
                continue
            tf = dt.count(t)
            if tf == 0:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            scores[i] += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
    return scores


def _rank(scores: list[float]) -> list[int]:
    """Indices ordered by descending score (only positive scores participate)."""
    return [i for i, _ in sorted(enumerate(scores), key=lambda p: p[1], reverse=True) if scores[i] > 0]


def rrf_fuse(*ranked_lists: list[int], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion over several ranked index lists."""
    fused: dict[int, float] = {}
    for ranking in ranked_lists:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return fused


def hybrid_order(dense: list[float], sparse: list[float], *, k: int = 60) -> list[int]:
    """Return document indices best-first by fusing dense (cosine) and sparse (BM25) rankings."""
    fused = rrf_fuse(_rank(dense), _rank(sparse), k=k)
    return [idx for idx, _ in sorted(fused.items(), key=lambda p: p[1], reverse=True)]
