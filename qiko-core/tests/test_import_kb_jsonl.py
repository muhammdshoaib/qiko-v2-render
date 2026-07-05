import json

from scripts.import_kb_jsonl import parse_jsonl_docs


def test_parse_jsonl_docs_skips_blank_lines_and_empty_text(tmp_path):
    p = tmp_path / "corpus.jsonl"
    p.write_text(
        "\n".join([
            json.dumps({"filename": "a.docx", "text": "hello world"}),
            "",
            json.dumps({"filename": "b.pdf", "text": "   "}),  # blank text -> skipped
            json.dumps({"source": "c/d.pptx", "text": "slide content"}),  # no filename -> uses source
            json.dumps({"text": "no id at all"}),  # neither -> falls back to doc-<i>
        ])
    )
    docs = list(parse_jsonl_docs(str(p)))
    assert docs == [
        ("a.docx", "hello world"),
        ("c/d.pptx", "slide content"),
        ("doc-4", "no id at all"),
    ]
