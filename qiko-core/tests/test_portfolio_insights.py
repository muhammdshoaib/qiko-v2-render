import json

from app.core.tenancy import get_tenant
from app.modules.ai import usage
from app.modules.ai.gateway import LLMResponse
from app.modules.joseph_mews.portfolio_insights import (
    PropertyInsightRequest,
    generate_property_insight,
)
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


def _request(**overrides) -> PropertyInsightRequest:
    payload = {
        "requestId": "req-1",
        "investor": {"id": 45, "firstName": "Jane"},
        "property": {"id": 88, "name": "Marina Heights Unit 12B", "grossYieldPct": 6.2},
        "portfolioAverages": {"grossYieldPct": 5.4},
    }
    payload.update(overrides)
    return PropertyInsightRequest.model_validate(payload)


def test_generate_property_insight_parses_a_clean_response():
    raw = json.dumps({
        "summary": "This property's yield is 0.8pp ahead of your portfolio average.",
        "groundedIn": ["property.grossYieldPct", "portfolioAverages.grossYieldPct"],
    })
    result = generate_property_insight(_request(), _CannedProvider(raw))
    assert result is not None
    assert result.summary == "This property's yield is 0.8pp ahead of your portfolio average."
    assert result.groundedIn == ["property.grossYieldPct", "portfolioAverages.grossYieldPct"]


def test_generate_property_insight_handles_markdown_fenced_json():
    raw = json.dumps({"summary": "Strong yield here."})
    fenced = f"```json\n{raw}\n```"
    result = generate_property_insight(_request(), _CannedProvider(fenced))
    assert result.summary == "Strong yield here."


def test_generate_property_insight_returns_none_on_non_json():
    result = generate_property_insight(_request(), _CannedProvider("not json at all"))
    assert result is None


def test_generate_property_insight_returns_none_when_the_provider_raises():
    result = generate_property_insight(_request(), _FailingProvider())
    assert result is None


def test_generate_property_insight_returns_none_on_a_blank_summary():
    raw = json.dumps({"summary": "   "})
    result = generate_property_insight(_request(), _CannedProvider(raw))
    assert result is None


def test_generate_property_insight_defaults_grounded_in_to_an_empty_list():
    raw = json.dumps({"summary": "Strong yield here."})
    result = generate_property_insight(_request(), _CannedProvider(raw))
    assert result.groundedIn == []


def test_generate_property_insight_has_no_suggested_action_field():
    # Deliberate: investor-facing, unlike signal_summary's admin-facing suggestedNextAction.
    raw = json.dumps({"summary": "Strong yield here."})
    result = generate_property_insight(_request(), _CannedProvider(raw))
    assert not hasattr(result, "suggestedNextAction")


def test_generate_property_insight_attributes_cost_to_the_shared_joseph_mews_agent():
    provider = _CannedProvider(json.dumps({"summary": "Strong yield here."}))
    generate_property_insight(_request(), provider)
    assert provider.seen_agent == AGENT_ID == "joseph-mews"
    assert provider.seen_tenant == TENANT == "joseph-mews"


def test_generate_property_insight_resets_the_binding_after_returning():
    provider = _CannedProvider(json.dumps({"summary": "Strong yield here."}))
    generate_property_insight(_request(), provider)
    assert usage.get_agent() is None
    assert get_tenant() is None


def test_system_prompt_forbids_suggested_actions_and_mortgage_or_projection_detail():
    provider = _CannedProvider(json.dumps({"summary": "Strong yield here."}))
    generate_property_insight(_request(), provider)
    assert "not suggest any action" in provider.seen_system
    assert "mortgage" in provider.seen_system.lower()


def test_generate_property_insight_uses_the_agents_config_when_supplied():
    provider = _CannedProvider(json.dumps({"summary": "Strong yield here."}))
    agent_config = {"guardrails": ["Never mention a competitor by name."]}
    generate_property_insight(_request(), provider, agent_config)
    assert "Never mention a competitor by name." in provider.seen_system
    # the fixed safety constraint is never displaced by the agent's own guardrails
    assert "not suggest any action" in provider.seen_system


def test_generate_property_insight_falls_back_when_agent_config_is_none():
    provider = _CannedProvider(json.dumps({"summary": "Strong yield here."}))
    generate_property_insight(_request(), provider, None)
    assert "Use ONLY the facts explicitly supplied to you" in provider.seen_system


def test_request_defaults_investor_and_portfolio_averages_to_empty():
    request = PropertyInsightRequest.model_validate({
        "requestId": "req-2", "property": {"id": 1, "grossYieldPct": 5.0},
    })
    assert request.investor == {}
    assert request.portfolioAverages == {}
