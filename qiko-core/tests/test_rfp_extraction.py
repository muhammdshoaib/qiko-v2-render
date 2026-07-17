import io
import json

import pytest

from app.modules.ai.gateway import LLMResponse
from app.modules.rfp.extraction import (
    MAX_ITEMS,
    MAX_SUBS,
    ExtractionError,
    chunk_document,
    ensure_unique_codes,
    extract_requirements,
    split_subsections,
)

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


async def _stub_assemble_worker(**_kw):
    """Fake worker for the background job's drafts stage: returns a StubProvider-style result so the
    drafts stage short-circuits (marked "error", nothing persisted) without a real LLM/network call.
    Extraction-focused tests only care about requirements/sections, not drafts."""
    from app.modules.agentcore.models import AgentResult, Critique, Decision

    class _W:
        async def answer(self, rid, text, **__):
            return AgentResult(requirement_id=rid, answer="", critique=Critique(grounding=0.0),
                               decision=Decision.human_review, citations=[], stub=True)
    return _W()


def _patch_generation(monkeypatch, provider):
    """Point the background job's extraction/brief/compliance at `provider` and its drafts stage at
    the stub worker, so an eager /extract runs fast and offline."""
    monkeypatch.setattr("app.modules.rfp.generation.get_provider", lambda **_kw: provider)
    monkeypatch.setattr("app.modules.rfp.generation.assemble_worker", _stub_assemble_worker)


def test_extract_requirements_parses_clean_json():
    items = extract_requirements("some tender text", _CannedProvider(SAMPLE_JSON))
    assert len(items) == 2
    assert items[0] == {"id": "A1", "title": "Company Profile", "classification": "KB",
                        "requirement": "Describe your company's experience in security services.",
                        "subsections": []}
    assert items[1]["classification"] == "MANUAL"


def test_extract_requirements_returns_explicit_subsections():
    """The structured schema: a top-level section carries an EXPLICIT `subsections` array; each is
    assigned a deterministic hierarchical code "{parent}.{n}" so the tree/rollups can group it."""
    raw = json.dumps([{
        "id": "B1", "title": "Organisational Structure", "classification": "KB",
        "requirement": "Describe your organisation.",
        "subsections": [
            {"title": "Organogram", "classification": "KB", "requirement": "Provide an org chart."},
            {"title": "Management", "classification": "DATA", "requirement": "Provide CVs."},
        ],
    }])
    items = extract_requirements("tender text", _CannedProvider(raw))
    assert len(items) == 1
    sec = items[0]
    assert sec["id"] == "B1" and sec["title"] == "Organisational Structure"
    assert [s["id"] for s in sec["subsections"]] == ["B1.1", "B1.2"]
    assert [s["title"] for s in sec["subsections"]] == ["Organogram", "Management"]
    assert sec["subsections"][1]["classification"] == "DATA"


def test_extract_requirements_drops_malformed_subsections_keeps_section():
    """A single bad sub-section (empty requirement) is dropped WITHOUT sinking its section or the
    other, well-formed sub-sections -- codes stay contiguous for the survivors."""
    raw = json.dumps([{
        "id": "B1", "title": "Section", "classification": "KB", "requirement": "Do it.",
        "subsections": [
            {"title": "Good", "classification": "KB", "requirement": "answer this"},
            {"title": "Bad", "classification": "KB", "requirement": ""},  # dropped
            {"title": "", "classification": "KB", "requirement": "no title"},  # dropped
            {"title": "Also good", "classification": "KB", "requirement": "and this"},
        ],
    }])
    items = extract_requirements("tender text", _CannedProvider(raw))
    subs = items[0]["subsections"]
    assert [s["title"] for s in subs] == ["Good", "Also good"]
    assert [s["id"] for s in subs] == ["B1.1", "B1.2"]  # contiguous codes for survivors


def test_extract_requirements_handles_markdown_fenced_json():
    fenced = f"Here you go:\n```json\n{SAMPLE_JSON}\n```"
    items = extract_requirements("tender text", _CannedProvider(fenced))
    assert len(items) == 2


def test_extract_requirements_defaults_unknown_classification_to_kb():
    raw = json.dumps([{"id": "B1", "title": "Something", "classification": "WEIRD",
                       "requirement": "Do the thing."}])
    items = extract_requirements("tender text", _CannedProvider(raw))
    assert items[0]["classification"] == "KB"


def test_extract_requirements_drops_malformed_sections():
    """Section-level validators drop malformed elements (missing title) individually while keeping
    the well-formed ones."""
    raw = json.dumps([
        {"id": "A1", "title": "Good", "classification": "KB", "requirement": "answer this"},
        {"id": "A2", "classification": "KB", "requirement": "no title -> dropped"},
        {"id": "A3", "title": "Empty", "classification": "KB", "requirement": ""},  # no req, no subs
    ])
    items = extract_requirements("tender text", _CannedProvider(raw))
    assert [i["id"] for i in items] == ["A1"]


def test_extract_requirements_rejects_non_json():
    with pytest.raises(ExtractionError):
        extract_requirements("tender text", _CannedProvider("not json at all"))


def test_extract_requirements_retries_on_invalid_json_then_succeeds():
    """A first unparseable response is retried; the second, valid response is accepted."""
    class _FlakyProvider:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, *, system=None, temperature=0.2):
            self.calls += 1
            return LLMResponse(text="not json" if self.calls == 1 else SAMPLE_JSON)

    provider = _FlakyProvider()
    items = extract_requirements("tender text", provider)
    assert provider.calls == 2 and len(items) == 2


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


def test_extract_requirements_dedupes_colliding_top_level_ids():
    """M1: two sections the model returns with the SAME id but different titles must NOT collide.
    The second gets a suffixed code so codes (and their sub-section req_ids, the export/answer key)
    stay unique before questions are written."""
    raw = json.dumps([
        {"id": "B1", "title": "First", "classification": "KB", "requirement": "do first",
         "subsections": [{"title": "x", "classification": "KB", "requirement": "sub x"}]},
        {"id": "B1", "title": "Second", "classification": "KB", "requirement": "do second",
         "subsections": [{"title": "y", "classification": "KB", "requirement": "sub y"}]},
    ])
    items = extract_requirements("tender text", _CannedProvider(raw))
    assert [i["id"] for i in items] == ["B1", "B1-2"]
    # sub-section req_ids are re-derived from the de-duplicated parent code, so they can't collide
    assert items[0]["subsections"][0]["id"] == "B1.1"
    assert items[1]["subsections"][0]["id"] == "B1-2.1"


def test_ensure_unique_codes_suffixes_repeats_and_rewrites_sub_ids():
    """ensure_unique_codes is the shared guard used after validation AND after the chunked merge:
    repeated codes get contiguous suffixes and every sub id is re-derived from the final code."""
    out = ensure_unique_codes([
        {"id": "A1", "subsections": [{"id": "A1.1"}]},
        {"id": "A1", "subsections": [{"id": "A1.1"}, {"id": "A1.2"}]},
        {"id": "A1", "subsections": []},
    ])
    assert [s["id"] for s in out] == ["A1", "A1-2", "A1-3"]
    assert [s["id"] for s in out[1]["subsections"]] == ["A1-2.1", "A1-2.2"]


def test_extract_requirements_caps_subsections_per_section():
    """M2: sub-sections are capped per section (MAX_SUBS) so one over-eager section can't mint
    hundreds of sub-requirements (each a draft LLM call)."""
    subs = [{"title": f"Part {i}", "classification": "KB", "requirement": f"describe part {i}"}
            for i in range(30)]
    raw = json.dumps([{"id": "B1", "title": "Big", "classification": "KB",
                       "requirement": "describe.", "subsections": subs}])
    items = extract_requirements("tender text", _CannedProvider(raw))
    assert len(items[0]["subsections"]) == MAX_SUBS == 15
    assert [s["id"] for s in items[0]["subsections"]] == [f"B1.{i}" for i in range(1, 16)]


def test_extract_requirements_retries_on_transient_provider_error():
    """L2: a RAW provider error (timeout/throttle) -- not an ExtractionError -- on the first attempt
    is retried rather than propagating on attempt one."""
    class _TransientThenOk:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, *, system=None, temperature=0.2):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("provider read timeout")
            return LLMResponse(text=SAMPLE_JSON)

    provider = _TransientThenOk()
    items = extract_requirements("tender text", provider)
    assert provider.calls == 2 and len(items) == 2


def test_extract_requirements_caps_at_coarse_max_items():
    """idg's "Include at most 20 items": even if the model over-produces, extraction caps the
    catalogue at MAX_ITEMS so a tender stays a small COARSE set of top-level sections."""
    raw = json.dumps([{"id": f"R{i}", "title": f"Section {i}", "classification": "KB",
                       "requirement": f"Describe section {i}."} for i in range(40)])
    items = extract_requirements("tender text", _CannedProvider(raw))
    assert len(items) == MAX_ITEMS == 20


# --- split_subsections (port of idg-worker answer.py) ---
def test_split_subsections_prefers_dotted_headings():
    req = ("B1.1 Contractor's Organogram: provide an org chart.\n"
           "B1.2 Organisation: describe the management structure.")
    parts = split_subsections("B1", req)
    assert [p["sub_id"] for p in parts] == ["B1.1", "B1.2"]
    assert parts[0]["title"].startswith("B1.1")
    assert "org chart" in parts[0]["body"]


def test_split_subsections_falls_back_to_lettered_clauses():
    req = "(a) Provide method statements.\n(b) Provide a risk assessment."
    parts = split_subsections("A3", req)
    assert [p["sub_id"] for p in parts] == ["(a)", "(b)"]


def test_split_subsections_single_when_no_structure():
    parts = split_subsections("A1", "Describe your company's experience.")
    assert len(parts) == 1
    assert parts[0]["sub_id"] == "A1" and parts[0]["body"] == "Describe your company's experience."


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
    # New async contract: /extract kicks off the background job and returns 202 + processing; the
    # Eager backend runs the job inline so requirements are populated by the time we poll.
    _patch_generation(monkeypatch, _CannedProvider(SAMPLE_JSON))

    c = auth_cookies("extractco", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender X"}, cookies=c).json()

    upload = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                         files={"file": ("tender.txt", io.BytesIO(b"tender document text"), "text/plain")})
    assert upload.status_code == 202
    assert upload.json()["status"] == "processing"

    listed = client.get(f"/api/v1/rfp/packs/{pack['id']}/requirements", cookies=c).json()
    assert len(listed) == 2
    assert {r["req_id"] for r in listed} == {"A1", "A2"}

    status = client.get(f"/api/v1/rfp/packs/{pack['id']}/status", cookies=c).json()
    assert status["requirements"] == "ready" and status["sections"] == "ready"


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
    """A VERY large document (over MAX_CONTEXT_CHARS = 160k, the single-call budget) falls back to
    the chunked path: split into multiple chunks, each extracted independently and in parallel,
    with the results consolidated (deduped/merged by title) -- not truncated to one call's worth of
    the document. A typical (<=160k) tender instead uses one coarse extraction call."""
    marker_a, marker_b = "UNIQUE_MARKER_ALPHA", "UNIQUE_MARKER_BETA"
    # Two paragraphs, each ~98k chars, so the whole document (~196k) exceeds the 160k single-call
    # budget and is guaranteed to split into several chunks -- one containing each marker.
    big_doc = (marker_a + " " + "filler " * 14000) + "\n\n" + (marker_b + " " + "filler " * 14000)

    class _RespondingByMarker:
        def generate(self, prompt, *, system=None, temperature=0.2):
            if marker_a in prompt:
                return LLMResponse(text=json.dumps([{"id": "A1", "title": "From chunk A",
                                                      "classification": "KB", "requirement": "req a"}]))
            if marker_b in prompt:
                return LLMResponse(text=json.dumps([{"id": "B1", "title": "From chunk B",
                                                      "classification": "KB", "requirement": "req b"}]))
            return LLMResponse(text="[]")

    _patch_generation(monkeypatch, _RespondingByMarker())
    c = auth_cookies("extractco4", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Big Tender"}, cookies=c).json()

    upload = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                         files={"file": ("big.txt", io.BytesIO(big_doc.encode()), "text/plain")})
    assert upload.status_code == 202
    ids = {item["req_id"] for item in client.get(f"/api/v1/rfp/packs/{pack['id']}/requirements", cookies=c).json()}
    assert {"A1", "B1"}.issubset(ids)  # both chunks' requirements made it into the merged result


def _fake_httpx_get(status_code=200, content=b"", headers=None):
    import httpx

    def fake_get(url, **kwargs):
        return httpx.Response(status_code, content=content, headers=headers or {}, request=httpx.Request("GET", url))
    return fake_get


def test_rfp_extract_url_fetches_and_extracts(client, monkeypatch):
    _patch_generation(monkeypatch, _CannedProvider(SAMPLE_JSON))
    monkeypatch.setattr("socket.gethostbyname", lambda host: "93.184.216.34")  # a public IP, no real DNS
    html = b"<html><body><h1>Tender</h1><p>Describe your experience.</p></body></html>"
    monkeypatch.setattr("httpx.get", _fake_httpx_get(200, html, {"content-type": "text/html"}))

    c = auth_cookies("urlco", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tender from URL"}, cookies=c).json()
    r = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract-url", cookies=c, json={"url": "https://tenders.example.com/boc-2171"})
    assert r.status_code == 202
    assert r.json()["status"] == "processing"
    assert len(client.get(f"/api/v1/rfp/packs/{pack['id']}/requirements", cookies=c).json()) == 2

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
    # > 160k so the chunked fallback path runs (one good chunk, one that fails to parse).
    big_doc = (marker_a + " " + "filler " * 14000) + "\n\n" + ("BAD_CHUNK " + "filler " * 14000)

    class _OneChunkFails:
        def generate(self, prompt, *, system=None, temperature=0.2):
            if marker_a in prompt:
                return LLMResponse(text=json.dumps([{"id": "A1", "title": "Good", "classification": "KB",
                                                      "requirement": "req a"}]))
            return LLMResponse(text="not valid json at all")  # this chunk always fails to parse

    _patch_generation(monkeypatch, _OneChunkFails())
    c = auth_cookies("extractco5", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Partial Tender"}, cookies=c).json()

    upload = client.post(f"/api/v1/rfp/packs/{pack['id']}/extract", cookies=c,
                         files={"file": ("big.txt", io.BytesIO(big_doc.encode()), "text/plain")})
    assert upload.status_code == 202
    ids = {item["req_id"] for item in client.get(f"/api/v1/rfp/packs/{pack['id']}/requirements", cookies=c).json()}
    assert "A1" in ids  # the good chunk's requirement survives even though the other chunk failed
