"""Text chunking for ingestion. Splits on paragraph boundaries, packing into ~max_chars windows
with a small overlap so context is not lost across chunk edges."""
from __future__ import annotations


def chunk_text(text: str, *, max_chars: int = 800, overlap: int = 100) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if buf and len(buf) + len(para) + 2 > max_chars:
            chunks.append(buf)
            buf = (buf[-overlap:] + "\n\n" + para) if overlap else para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks
