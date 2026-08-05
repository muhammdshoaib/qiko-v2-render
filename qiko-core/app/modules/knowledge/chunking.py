"""Text chunking for ingestion. Splits on paragraph boundaries, packing into ~max_chars windows
with a small overlap so context is not lost across chunk edges.

A paragraph larger than the window is hard-split rather than emitted whole. Without that, a document
with no blank lines became ONE chunk of unlimited size: the largest passage observed in production was
149,579 characters against a 800-character window, because a PDF text extraction produced no paragraph
breaks at all. Such a chunk defeats the entire point of chunking (a match should point at a specific
passage, not at a whole document) and it also exceeds the embedding provider's hard input limits.
"""
from __future__ import annotations

_MIN_WINDOW = 50


def _hard_split(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split text that has no usable paragraph boundary, preferring whitespace over mid-word cuts."""
    pieces: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            # Back off to the last whitespace in the final quarter of the window, so a cut lands
            # between words where possible without shrinking the window dramatically.
            window = text[start:end]
            pivot = window.rfind(" ", int(max_chars * 0.75))
            if pivot > 0:
                end = start + pivot
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        # Overlap backwards from the cut so a sentence spanning the boundary is still retrievable.
        start = max(end - overlap, start + 1)
    return pieces


def chunk_text(text: str, *, max_chars: int = 800, overlap: int = 100) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    max_chars = max(_MIN_WINDOW, int(max_chars))
    # An overlap at or above the window would make no forward progress.
    overlap = max(0, min(int(overlap), max_chars // 2))

    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if len(para) > max_chars:
            # Flush what is buffered, then split the oversized paragraph on its own.
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_hard_split(para, max_chars, overlap))
            continue
        if buf and len(buf) + len(para) + 2 > max_chars:
            chunks.append(buf)
            buf = (buf[-overlap:] + "\n\n" + para) if overlap else para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    # The overlap prefix can push a packed chunk slightly past the window, so enforce the ceiling
    # once at the end. This is the guarantee callers and the embedding provider actually rely on.
    ceiling = max_chars + overlap
    if any(len(chunk) > ceiling for chunk in chunks):
        bounded: list[str] = []
        for chunk in chunks:
            bounded.extend([chunk] if len(chunk) <= ceiling else _hard_split(chunk, max_chars, overlap))
        chunks = bounded
    return chunks
