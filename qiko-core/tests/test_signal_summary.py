import json

from app.core.tenancy import get_tenant
from app.modules.ai import usage
from app.modules.ai.gateway import LLMResponse
from app.modules.joseph_mews.signal_summary import SignalSummarizeRequest, summarize_signal
from app.modules.joseph_mews.worker import AGENT_ID, TENANT


class _CannedProvider:
    def __init__(self, text: str):
        self.text = text
        self.seen_agent: str | None = "not called"
        self.seen_tenant: str | None = "not called"
        self.seen_system: str | None = None

    def generate(self, prompt, *, system=None, temperature=0.2, prefill=None):
        self.seen_agent = usage.get_agent()
        self.seen_tenant = get_tenant()
        self.seen_system = system
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


def test_summarize_signal_attributes_cost_to_the_shared_joseph_mews_agent():
    # 2 Sep, Razvan: "same worker, same config, one cost bucket" - generate() must see the same
    # agent_id/tenant Worker.answer() binds, or this spend is recorded as unattributed.
    provider = _CannedProvider(json.dumps({"summary": "Strong interest.", "suggestedNextAction": "Follow up."}))
    summarize_signal(_request(), provider)
    assert provider.seen_agent == AGENT_ID == "joseph-mews"
    assert provider.seen_tenant == TENANT == "joseph-mews"


def test_summarize_signal_resets_the_binding_after_returning():
    provider = _CannedProvider(json.dumps({"summary": "Strong interest.", "suggestedNextAction": "Follow up."}))
    summarize_signal(_request(), provider)
    assert usage.get_agent() is None
    assert get_tenant() is None


def test_summarize_signal_uses_the_agents_config_when_supplied():
    provider = _CannedProvider(json.dumps({"summary": "Strong interest.", "suggestedNextAction": "Follow up."}))
    agent_config = {"guardrails": ["Never mention a competitor by name."]}
    summarize_signal(_request(), provider, agent_config)
    assert "Never mention a competitor by name." in provider.seen_system


def test_summarize_signal_falls_back_when_agent_config_is_none():
    provider = _CannedProvider(json.dumps({"summary": "Strong interest.", "suggestedNextAction": "Follow up."}))
    summarize_signal(_request(), provider, None)
    assert "Use ONLY the facts explicitly supplied to you" in provider.seen_system
