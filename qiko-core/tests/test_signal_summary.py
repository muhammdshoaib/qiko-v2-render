import json

from app.modules.ai.gateway import LLMResponse
from app.modules.joseph_mews.signal_summary import SignalSummarizeRequest, summarize_signal


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        return LLMResponse(text=self.text)


class _FailingProvider:
    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        raise AttributeError("network is down")


def _request(**overrides) -> SignalSummarizeRequest:
    payload = {
        "requestId": "req-1",
        "signal": {
            "id": 123, "signalType": "property_revisit",
            "triggeringActivity": "Viewed Property Detail 3x in 24h", "intentLevel": "high",
        },
        "investor": {"id": 45, "firstName": "Jane", "investmentPreferences": "Birmingham apartments"},
        "property": {"id": 88, "name": "Marina Heights Unit 12B", "projectedGrossYield": 6.2},
    }
    payload.update(overrides)
    return SignalSummarizeRequest.model_validate(payload)


def test_summarize_signal_parses_a_clean_response():
    raw = json.dumps({
        "summary": "Jane viewed Marina Heights three times, suggesting strong interest.",
        "suggestedNextAction": "Call Jane about Marina Heights.",
        "groundedIn": ["signal.triggeringActivity", "investor.investmentPreferences"],
    })
    result = summarize_signal(_request(), _CannedProvider(raw))
    assert result is not None
    assert result.summary == "Jane viewed Marina Heights three times, suggesting strong interest."
    assert result.suggestedNextAction == "Call Jane about Marina Heights."
    assert result.groundedIn == ["signal.triggeringActivity", "investor.investmentPreferences"]


def test_summarize_signal_handles_markdown_fenced_json():
    raw = json.dumps({"summary": "Strong interest.", "suggestedNextAction": "Follow up."})
    fenced = f"Here you go:\n```json\n{raw}\n```"
    result = summarize_signal(_request(), _CannedProvider(fenced))
    assert result.summary == "Strong interest."


def test_summarize_signal_returns_none_on_non_json():
    result = summarize_signal(_request(), _CannedProvider("not json at all"))
    assert result is None


def test_summarize_signal_returns_none_when_the_provider_raises():
    result = summarize_signal(_request(), _FailingProvider())
    assert result is None


def test_summarize_signal_returns_none_on_a_blank_summary():
    raw = json.dumps({"summary": "   ", "suggestedNextAction": "Follow up."})
    result = summarize_signal(_request(), _CannedProvider(raw))
    assert result is None


def test_summarize_signal_defaults_grounded_in_to_an_empty_list():
    raw = json.dumps({"summary": "Strong interest.", "suggestedNextAction": "Follow up."})
    result = summarize_signal(_request(), _CannedProvider(raw))
    assert result.groundedIn == []


def test_request_accepts_a_signal_with_no_property_or_development():
    request = _request(property=None)
    assert request.property is None
    assert request.development is None
