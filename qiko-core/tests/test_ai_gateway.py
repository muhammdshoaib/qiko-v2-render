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


# --- provider selection from config ---
def test_build_one():
    assert isinstance(_build_one("stub"), StubProvider)
    assert isinstance(_build_one("bedrock"), BedrockProvider)


def test_get_provider_wraps_bedrock_with_stub_fallback():
    p = get_provider()  # default config: bedrock + stub fallback
    assert isinstance(p, FallbackProvider)
    assert isinstance(p.primary, BedrockProvider)
    assert isinstance(p.fallback, StubProvider)


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
