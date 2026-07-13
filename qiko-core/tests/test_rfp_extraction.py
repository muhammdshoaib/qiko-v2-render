import io
import json

import pytest

from app.modules.ai.gateway import LLMResponse
from app.modules.rfp.extraction import ExtractionError, chunk_document, extract_requirements

from tests.helpers import auth_cookies

SAMPLE_JSON = json.dumps([
    {"id": "A1", "title": "Company Profile", "classification": "KB",
     "requirement": "Describe your company's experience in security services."},
    {"id": "A2", "title": "Pricing", "classification": "MANUAL",
     "requirement": "Complete the pricing schedule in the prescribed format."},
])


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2):
        return LLMResponse(text=self.text)


def test_extract_requirements_parses_clean_json():
    items = extract_requirements("some tender text", _CannedProvider(SAMPLE_JSON))
    assert len(items) == 2
    assert items[0] == {"id": "A1", "title": "Company Profile", "classification": "KB",
                        "requirement": "Describe your company's experience in security services."}
    assert items[1]["classification"] == "MANUAL"


def test_extract_requirements_handles_markdown_fenced_json():
    fenced = f"Here you go:\n```json\n{SAMPLE_JSON}\n```"
    items = extract_requirements("tender text", _CannedProvider(fenced))
    assert len(items) == 2


def test_extract_requirements_defaults_unknown_classification_to_kb():
    raw = json.dumps([{"id": "B1", "title": "Something", "classification": "WEIRD",
                       "requirement": "Do the thing."}])
    items = extract_requirements("tender text", _CannedProvider(raw))
    assert items[0]["classification"] == "KB"


def test_extract_requirements_rejects_non_json():
    with pytest.raises(ExtractionError):
        extract_requirements("tender text", _CannedProvider("not json at all"))


def test_extract_requirements_rejects_empty_array():
    with pytest.raises(ExtractionError):
        extract_requirements("tender text", _CannedProvider("[]"))


def test_extract_requirements_id_prefix_disambiguates_fallback_ids():
    # No "id" in either item -- both would fall back to "R1"/"R2" without a prefix, colliding
    # with another chunk's fallback ids once merged (see _extract_requirements_chunked).
    raw = json.dumps([{"title": "A", "classification": "KB", "requirement": "do a"},
                      {"title": "B", "classification": "KB", "requirement": "do b"}])
    items = extract_requirements("tender text", _CannedProvider(raw), id_prefix="c3-")
    assert [i["id"] for i in items] == ["c3-R1", "c3-R2"]


# --- chunk_document ---
def test_chunk_document_returns_single_chunk_for_short_text():
    assert chunk_document("short document", max_chars=1000) == ["short document"]


def test_chunk_document_splits_long_text_into_overlapping_chunks():
    text = "\n\n".join(f"Section {i}. " + ("word " * 200) for i in range(20))
    chunks = chunk_document(text, max_chars=2000, overlap_chars=200)
    assert len(chunks) > 1
    # every chunk fits the budget (the paragraph-boundary search can only shrink it, not grow it)
    assert all(len(c) <= 2000 for c in chunks)
    # consecutive chunks overlap: the tail of one reappears at the head of the next
    for a, b in zip(chunks, chunks[1:]):
        assert a[-100:] in b or b.startswith(a[-50:])


def test_chunk_document_prefers_paragraph_boundaries():
    text = ("A" * 900) + "\n\n" + ("B" * 900) + "\n\n" + ("C" * 900)
    chunks = chunk_document(text, max_chars=1000, overlap_chars=50)
    # each chunk should end right at a paragraph boundary, not mid-run of letters
    assert chunks[0].rstrip("\n") == "A" * 900
    assert all(len(c) <= 1000 for c in chunks)


def test_chunk_document_covers_the_whole_document():
    text = "\n\n".join(f"para {i} " + ("x" * 500) for i in range(15))
    chunks = chunk_document(text, max_chars=1500, overlap_chars=100)
    assert "".join(chunks[0:1])[:20] == text[:20]  # starts at the beginning
    assert text[-20:] in chunks[-1]  # the tail is covered by the last chunk


# --- API-level: full upload -> extract -> list round trip ---
def test_rfp_extract_endpoint_round_trip(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(SAMPLE_JSON))

    c = auth_cookies("extractco", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender X"}, cookies=c).json()

    upload = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                         files={"file": ("tender.txt", io.BytesIO(b"tender document text"), "text/plain")})
    assert upload.status_code == 200
    extracted = upload.json()
    assert len(extracted) == 2
    assert extracted[0]["req_id"] == "A1"

    listed = client.get(f"/api/v1/rfp/packs/{pack['id']}/requirements", cookies=c).json()
    assert len(listed) == 2


def test_rfp_extract_rejects_unsupported_file_type(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(SAMPLE_JSON))
    c = auth_cookies("extractco2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender Y"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                    files={"file": ("tender.exe", io.BytesIO(b"binary"), "application/octet-stream")})
    assert r.status_code == 422


def test_rfp_extract_404_for_missing_pack(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(SAMPLE_JSON))
    c = auth_cookies("extractco3", "owner")
    r = client.post("/api/v1/rfp/packs/missing/extract", cookies=c,
                    files={"file": ("tender.txt", io.BytesIO(b"text"), "text/plain")})
    assert r.status_code == 404


def test_rfp_extract_chunks_a_large_document_and_merges_results(client, monkeypatch):
    """A document over chunk_document's default max_chars (25k) must be split into multiple
    chunks, each extracted independently and in parallel, with the results merged -- not
    truncated to one call's worth of the document like before."""
    marker_a, marker_b = "UNIQUE_MARKER_ALPHA", "UNIQUE_MARKER_BETA"
    # Two paragraphs, each padded well past the chunk budget on its own, so this document is
    # guaranteed to split into (at least) two chunks -- one containing each marker.
    big_doc = (marker_a + " " + "filler " * 6000) + "\n\n" + (marker_b + " " + "filler " * 6000)

    class _RespondingByMarker:
        def generate(self, prompt, *, system=None, temperature=0.2):
            if marker_a in prompt:
                return LLMResponse(text=json.dumps([{"id": "A1", "title": "From chunk A",
                                                      "classification": "KB", "requirement": "req a"}]))
            if marker_b in prompt:
                return LLMResponse(text=json.dumps([{"id": "B1", "title": "From chunk B",
                                                      "classification": "KB", "requirement": "req b"}]))
            return LLMResponse(text="[]")

    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _RespondingByMarker())
    c = auth_cookies("extractco4", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Big Tender"}, cookies=c).json()

    upload = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                         files={"file": ("big.txt", io.BytesIO(big_doc.encode()), "text/plain")})
    assert upload.status_code == 200
    ids = {item["req_id"] for item in upload.json()}
    assert {"A1", "B1"}.issubset(ids)  # both chunks' requirements made it into the merged result


def _fake_httpx_get(status_code=200, content=b"", headers=None):
    import httpx

    def fake_get(url, **kwargs):
        return httpx.Response(status_code, content=content, headers=headers or {}, request=httpx.Request("GET", url))
    return fake_get


def test_rfp_extract_url_fetches_and_extracts(client, monkeypatch):
    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _CannedProvider(SAMPLE_JSON))
    monkeypatch.setattr("socket.gethostbyname", lambda host: "93.184.216.34")  # a public IP, no real DNS
    html = b"<html><body><h1>Tender</h1><p>Describe your experience.</p></body></html>"
    monkeypatch.setattr("httpx.get", _fake_httpx_get(200, html, {"content-type": "text/html"}))

    c = auth_cookies("urlco", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender from URL"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract-url", cookies=c, json={"url": "https://tenders.example.com/boc-2171"})
    assert r.status_code == 200
    assert len(r.json()) == 2

    fetched = client.get(f"/api/v1/rfp/packs/{pack['id']}", cookies=c).json()
    assert "Describe your experience" in fetched["document_text"]


def test_rfp_extract_url_rejects_private_addresses(client):
    c = auth_cookies("urlco2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    for bad_url in ("http://localhost:8000/admin", "http://127.0.0.1/secret", "http://169.254.169.254/latest/meta-data/"):
        r = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract-url", cookies=c, json={"url": bad_url})
        assert r.status_code == 422, bad_url


def test_rfp_extract_url_rejects_non_http_scheme(client):
    c = auth_cookies("urlco3", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract-url", cookies=c, json={"url": "file:///etc/passwd"})
    assert r.status_code == 422


def test_rfp_extract_url_surfaces_fetch_failure(client, monkeypatch):
    import httpx

    monkeypatch.setattr("socket.gethostbyname", lambda host: "93.184.216.34")

    def fake_get(url, **kwargs):
        raise httpx.ConnectError("connection refused")
    monkeypatch.setattr("httpx.get", fake_get)

    c = auth_cookies("urlco4", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract-url", cookies=c, json={"url": "https://tenders.example.com/gone"})
    assert r.status_code == 422


def test_rfp_extract_url_404_for_missing_pack(client):
    c = auth_cookies("urlco5", "owner")
    r = client.post("/api/v1/rfp/packs/missing/extract-url", cookies=c, json={"url": "https://tenders.example.com/x"})
    assert r.status_code == 404


def test_rfp_extract_one_bad_chunk_does_not_sink_the_others(client, monkeypatch):
    marker_a = "UNIQUE_MARKER_GOOD"
    big_doc = (marker_a + " " + "filler " * 6000) + "\n\n" + ("BAD_CHUNK " + "filler " * 6000)

    class _OneChunkFails:
        def generate(self, prompt, *, system=None, temperature=0.2):
            if marker_a in prompt:
                return LLMResponse(text=json.dumps([{"id": "A1", "title": "Good", "classification": "KB",
                                                      "requirement": "req a"}]))
            return LLMResponse(text="not valid json at all")  # this chunk always fails to parse

    monkeypatch.setattr("app.modules.rfp.router.get_provider", lambda **_kw: _OneChunkFails())
    c = auth_cookies("extractco5", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Partial Tender"}, cookies=c).json()

    upload = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                         files={"file": ("big.txt", io.BytesIO(big_doc.encode()), "text/plain")})
    assert upload.status_code == 200
    ids = {item["req_id"] for item in upload.json()}
    assert "A1" in ids  # the good chunk's requirement survives even though the other chunk failed
