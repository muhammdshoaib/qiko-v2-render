import json

from app.modules.ai.gateway import LLMResponse
from app.modules.joseph_mews.extraction import extract_qualification
from app.modules.joseph_mews.qualification import FundingMethod, LeadQualification, Timeline


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        return LLMResponse(text=self.text)


class _FailingProvider:
    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        raise AttributeError("network is down")


def test_extract_qualification_parses_a_clean_response():
    raw = json.dumps({
        "timeline": "soon", "has_budget_signal": True, "funding_method": "cash",
        "journey_stage": "experienced", "interest_signal": True, "wants_human": False,
        "other_factors": 1,
    })
    result = extract_qualification("some conversation", _CannedProvider(raw))
    assert result == LeadQualification(
        timeline=Timeline.soon, has_budget_signal=True, funding_method=FundingMethod.cash,
        journey_stage="experienced", interest_signal=True, wants_human=False, other_factors=1,
    )


def test_extract_qualification_handles_markdown_fenced_json():
    raw = json.dumps({"timeline": "future"})
    fenced = f"Here you go:\n```json\n{raw}\n```"
    result = extract_qualification("some conversation", _CannedProvider(fenced))
    assert result.timeline is Timeline.future


def test_extract_qualification_defaults_unknown_enum_values_safely():
    raw = json.dumps({"timeline": "next-tuesday", "funding_method": "crypto"})
    result = extract_qualification("some conversation", _CannedProvider(raw))
    assert result.timeline is Timeline.unknown
    assert result.funding_method is FundingMethod.unknown


def test_extract_qualification_caps_other_factors_at_three():
    raw = json.dumps({"other_factors": 50})
    result = extract_qualification("some conversation", _CannedProvider(raw))
    assert result.other_factors == 3


def test_extract_qualification_falls_back_to_all_unknown_on_non_json():
    result = extract_qualification("some conversation", _CannedProvider("not json at all"))
    assert result == LeadQualification()


def test_extract_qualification_falls_back_when_the_provider_raises():
    result = extract_qualification("some conversation", _FailingProvider())
    assert result == LeadQualification()
