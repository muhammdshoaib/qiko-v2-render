"""The chunker emitted unbounded chunks (audit follow-up).

chunk_text packs paragraphs into a max_chars window, but it never split a paragraph that was itself
larger than the window. A PDF text extraction with no blank lines is one paragraph, so the whole
document became ONE chunk: the largest passage in production was 149,579 characters against an
800-character window. That defeats retrieval granularity (a match should point at a passage, not a
document) and it also exceeds the embedding provider's hard limits, which is what forced window
mean-pooling into the re-embed tool.
"""
from app.modules.knowledge.chunking import chunk_text


def test_a_document_with_no_paragraph_breaks_is_still_chunked():
    """This is the exact production shape: extracted PDF text with no blank lines."""
    text = "clause " * 25_000  # 175k characters, one paragraph
    chunks = chunk_text(text, max_chars=800, overlap=100)
    assert len(chunks) > 100
    assert max(len(chunk) for chunk in chunks) <= 900


def test_the_ceiling_holds_for_every_shape():
    shapes = {
        "one giant paragraph": "x" * 50_000,
        "no whitespace at all": "y" * 5_000,
        "giant paragraph among small ones": "short\n\n" + "z" * 9_000 + "\n\nshort again",
        "many small paragraphs": "\n\n".join(["para " * 20] * 200),
        "one long line of words": " ".join(["word"] * 20_000),
    }
    for name, text in shapes.items():
        chunks = chunk_text(text, max_chars=800, overlap=100)
        assert chunks, name
        assert max(len(chunk) for chunk in chunks) <= 900, f"{name}: {max(len(c) for c in chunks)}"


def test_no_content_is_lost():
    """A hard split must not drop text: the point is granularity, not truncation."""
    text = " ".join(f"token{index}" for index in range(3_000))
    chunks = chunk_text(text, max_chars=400, overlap=50)
    joined = " ".join(chunks)
    for index in (0, 1, 1499, 2999):
        assert f"token{index}" in joined


def test_a_cut_prefers_a_word_boundary():
    text = " ".join(["alpha"] * 500)
    chunks = chunk_text(text, max_chars=200, overlap=20)
    # No chunk should begin or end mid-word for text that is entirely whitespace-separated.
    for chunk in chunks[:-1]:
        assert not chunk.endswith("alph"), chunk[-10:]


def test_small_documents_are_untouched():
    """The common case must not change shape, or every existing corpus re-chunks differently."""
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert chunk_text("one short line") == ["one short line"]
    two = chunk_text("first para\n\nsecond para")
    assert two == ["first para\n\nsecond para"]


def test_paragraph_packing_is_still_preferred_over_hard_splitting():
    """Hard splitting is the fallback, not the strategy: paragraphs that fit must stay whole."""
    paras = ["para one is here", "para two is here", "para three is here"]
    chunks = chunk_text("\n\n".join(paras), max_chars=800, overlap=0)
    assert len(chunks) == 1
    for para in paras:
        assert para in chunks[0]


def test_a_degenerate_overlap_cannot_stall_the_split():
    """An overlap at or above the window would make no forward progress and loop forever."""
    chunks = chunk_text("q" * 5_000, max_chars=100, overlap=100)
    assert chunks and max(len(chunk) for chunk in chunks) <= 150


def test_a_tiny_window_is_floored_rather_than_looping():
    chunks = chunk_text("w" * 1_000, max_chars=1, overlap=0)
    assert chunks and max(len(chunk) for chunk in chunks) <= 60


def test_the_default_window_bounds_the_worst_observed_production_document():
    """149,579 characters was the real maximum. At the default settings it must become many chunks,
    every one of them embeddable."""
    chunks = chunk_text("a" * 149_579)
    assert len(chunks) > 150
    assert max(len(chunk) for chunk in chunks) <= 900
