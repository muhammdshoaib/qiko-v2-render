import math

from app.modules.ai.bedrock import BedrockProvider, resolve_model_id
from app.modules.ai.embeddings import LocalEmbeddings, get_embeddings
from app.modules.ai.gateway import (
    FallbackProvider,
    StubProvider,
    _build_one,
    get_provider,
)


# --- model id / inference profiles ---
def test_resolve_model_id_profiles():
    m = "anthropic.claude-sonnet-4-5"
    assert resolve_model_id(m, "eu") == "eu.anthropic.claude-sonnet-4-5"
    assert resolve_model_id(m, "us") == "us.anthropic.claude-sonnet-4-5"
    assert resolve_model_id(m, "global") == "global.anthropic.claude-sonnet-4-5"
    assert resolve_model_id(m, "") == m  # in-Region


def test_bedrock_provider_uses_config_defaults():
    p = BedrockProvider()
    assert p.model_id == "eu.anthropic.claude-sonnet-4-5"  # default profile 'eu'
    assert p.region == "eu-central-1"
    assert p.read_timeout == 20  # fast per-requirement hot path default


def test_bedrock_provider_read_timeout_override():
    # extraction/compliance/brief/ask are one-shot whole-document calls that need longer than the
    # per-requirement default -- see rfp/router.py's _DOCUMENT_READ_TIMEOUT.
    p = BedrockProvider(read_timeout=90)
    assert p.read_timeout == 90


# --- fallback ---
class _Boom:
    def generate(self, prompt, *, system=None, temperature=0.2):
        raise RuntimeError("bedrock unavailable")


def test_fallback_uses_secondary_on_failure():
    fb = FallbackProvider(_Boom(), StubProvider(canned="fallback answer"))
    assert fb.generate("x").text == "fallback answer"


def test_fallback_uses_primary_when_ok():
    fb = FallbackProvider(StubProvider(canned="primary"), StubProvider(canned="fb"))
    assert fb.generate("x").text == "primary"


def test_stub_provider_marks_output_as_stub():
    # Both the echo and canned paths are stub-sourced -- flagged so persistence paths can refuse
    # to store the output as a real grounded draft.
    assert StubProvider().generate("CONTEXT:\nx\n\nREQUIREMENT:\ny").stub is True
    assert StubProvider(canned="hi").generate("x").stub is True


def test_fallback_propagates_stub_flag_when_falling_back():
    # A Bedrock outage forces the stub fallback; the flag must survive so callers know the text
    # is not a real grounded answer.
    fb = FallbackProvider(_Boom(), StubProvider(canned="fallback answer"))
    r = fb.generate("x")
    assert r.text == "fallback answer" and r.stub is True


# --- provider selection from config ---
def test_build_one():
    assert isinstance(_build_one("stub"), StubProvider)
    assert isinstance(_build_one("bedrock"), BedrockProvider)


def test_get_provider_wraps_bedrock_with_stub_fallback():
    p = get_provider()  # default config: bedrock + stub fallback
    assert isinstance(p, FallbackProvider)
    assert isinstance(p.primary, BedrockProvider)
    assert isinstance(p.fallback, StubProvider)


def test_get_provider_read_timeout_override_reaches_bedrock_provider():
    p = get_provider(read_timeout=90)
    assert isinstance(p, FallbackProvider)
    assert p.primary.read_timeout == 90


# --- embeddings ---
def test_local_embeddings_deterministic_and_normalised():
    e = LocalEmbeddings(dim=16)
    v1 = e.embed("iso 9001 certification")
    v2 = e.embed("iso 9001 certification")
    assert v1 == v2
    assert len(v1) == 16
    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0, rel_tol=1e-9)


def test_local_embeddings_empty_is_zero_vector():
    e = LocalEmbeddings(dim=8)
    assert e.embed("") == [0.0] * 8


def test_get_embeddings_defaults_local():
    e = get_embeddings()
    assert isinstance(e, LocalEmbeddings)
    assert e.dim == 1024
