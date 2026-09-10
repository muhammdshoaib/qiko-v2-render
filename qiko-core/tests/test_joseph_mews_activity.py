import json

from app.modules.joseph_mews.activity import (
    MIN_CALCULATOR_VISITS_FOR_SIGNAL,
    MIN_PROPERTY_VISITS_FOR_SIGNAL,
    ActivityEvent,
    IntentSignalRequest,
    aggregate_activity,
    generate_intent_signals,
    has_signal_worthy_evidence,
)


def _event(category, label, *, property_name=None, location=None, postcode=None):
    return ActivityEvent(
        category=category, label=label, property_name=property_name, location=location,
        postcode=postcode,
    )


class _FakeProvider:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate(self, prompt, *, system, temperature, prefill=""):
        self.calls.append({"prompt": prompt, "system": system})
        return type("R", (), {"text": self.text})()


# Evidence that clears the deterministic eligibility guardrail (see the "signal-eligibility
# guardrail" tests below) -- used by tests below this point that are exercising response
# parsing/error-handling, not the guardrail itself, so they need the LLM to actually be called.
_ELIGIBLE_ACTIVITY = {
    "properties": [{"propertyName": "X", "location": "Manchester", "postcode": "M1 1AA", "visitCount": 5}],
}


def test_aggregate_counts_screen_visits():
    events = [_event("screen", "PropertyDetail"), _event("screen", "PropertyDetail"),
             _event("screen", "Dashboard")]
    agg = aggregate_activity(events)
    assert agg["screens"] == {"PropertyDetail": 2, "Dashboard": 1}


def test_aggregate_groups_property_visits_by_name_location_postcode_never_id():
    events = [
        _event("property_visit", "PropertyDetail", property_name="The Mayfair Residence",
              location="Mount Street, Mayfair", postcode="W1K 2HQ"),
        _event("property_visit", "PropertyDetail", property_name="The Mayfair Residence",
              location="Mount Street, Mayfair", postcode="W1K 2HQ"),
    ]
    agg = aggregate_activity(events)
    assert agg["properties"] == [{
        "propertyName": "The Mayfair Residence", "location": "Mount Street, Mayfair",
        "postcode": "W1K 2HQ", "visitCount": 2,
    }]


def test_aggregate_counts_calculator_steps():
    events = [_event("calculator_step", "projection"), _event("calculator_step", "projection"),
             _event("calculator_step", "deposit")]
    agg = aggregate_activity(events)
    assert agg["calculatorSteps"] == {"projection": 2, "deposit": 1}


def test_aggregate_never_leaks_a_property_id_shaped_field():
    events = [_event("property_visit", "PropertyDetail", property_name="JM-001",
                     location="Leeds", postcode="LS1 1AA")]
    agg = aggregate_activity(events)
    assert "propertyId" not in json.dumps(agg)
    assert "id" not in agg["properties"][0]


def test_generate_intent_signals_parses_a_clean_response():
    provider = _FakeProvider(json.dumps({
        "signals": [{
            "signal": "Interested in Manchester property", "strength": "high",
            "evidence": "Manchester-area property viewed 5x", "category": "location_interest",
        }],
    }))
    request = IntentSignalRequest(
        requestId="r1", investorRef="inv-1",
        activity={"properties": [{"propertyName": "X", "location": "Manchester",
                                  "postcode": "M1 1AA", "visitCount": 5}]},
    )
    result = generate_intent_signals(request, provider)
    assert result is not None
    assert result.signals[0].signal == "Interested in Manchester property"
    assert result.signals[0].strength == "high"


def test_generate_intent_signals_handles_markdown_fenced_json():
    provider = _FakeProvider(
        '```json\n{"signals": [{"signal": "s", "strength": "low", "evidence": "e"}]}\n```'
    )
    request = IntentSignalRequest(requestId="r1", investorRef="inv-1", activity=_ELIGIBLE_ACTIVITY)
    result = generate_intent_signals(request, provider)
    assert result is not None
    assert result.signals[0].signal == "s"


def test_generate_intent_signals_returns_none_on_non_json():
    provider = _FakeProvider("not json at all")
    request = IntentSignalRequest(requestId="r1", investorRef="inv-1", activity=_ELIGIBLE_ACTIVITY)
    assert generate_intent_signals(request, provider) is None


def test_generate_intent_signals_returns_none_when_provider_raises():
    class _RaisingProvider:
        def generate(self, *a, **k):
            raise AttributeError("network is down")

    request = IntentSignalRequest(requestId="r1", investorRef="inv-1", activity=_ELIGIBLE_ACTIVITY)
    assert generate_intent_signals(request, _RaisingProvider()) is None


def test_generate_intent_signals_with_no_signals_returns_empty_list_not_none():
    provider = _FakeProvider(json.dumps({"signals": []}))
    request = IntentSignalRequest(requestId="r1", investorRef="inv-1", activity={})
    result = generate_intent_signals(request, provider)
    assert result is not None
    assert result.signals == []


# --- deterministic signal-eligibility guardrail -------------------------------------------


def test_screen_visits_alone_are_never_signal_worthy_no_matter_how_many():
    """Jake's own example: repeated passive browsing (screens, and by the same logic anything
    that isn't a property or calculator engagement) must never manufacture a signal on its own,
    no matter the count - only repeated *property* or *calculator* engagement can."""
    aggregated = {"screens": {"Dashboard": 500}, "calculatorSteps": {}, "properties": []}
    assert has_signal_worthy_evidence(aggregated) is False


def test_property_visits_below_threshold_are_not_signal_worthy():
    aggregated = {
        "screens": {}, "calculatorSteps": {},
        "properties": [{"propertyName": "X", "location": "Leeds", "postcode": "LS1 1AA",
                        "visitCount": MIN_PROPERTY_VISITS_FOR_SIGNAL - 1}],
    }
    assert has_signal_worthy_evidence(aggregated) is False


def test_property_visits_at_threshold_are_signal_worthy():
    aggregated = {
        "screens": {}, "calculatorSteps": {},
        "properties": [{"propertyName": "X", "location": "Leeds", "postcode": "LS1 1AA",
                        "visitCount": MIN_PROPERTY_VISITS_FOR_SIGNAL}],
    }
    assert has_signal_worthy_evidence(aggregated) is True


def test_calculator_steps_at_threshold_are_signal_worthy():
    aggregated = {
        "screens": {}, "calculatorSteps": {"projection": MIN_CALCULATOR_VISITS_FOR_SIGNAL},
        "properties": [],
    }
    assert has_signal_worthy_evidence(aggregated) is True


def test_calculator_steps_below_threshold_are_not_signal_worthy():
    aggregated = {
        "screens": {}, "calculatorSteps": {"projection": MIN_CALCULATOR_VISITS_FOR_SIGNAL - 1},
        "properties": [],
    }
    assert has_signal_worthy_evidence(aggregated) is False


def test_empty_activity_is_not_signal_worthy():
    assert has_signal_worthy_evidence({"screens": {}, "calculatorSteps": {}, "properties": []}) is False


def test_generate_intent_signals_skips_the_llm_call_entirely_when_nothing_is_eligible():
    """The guardrail must stop noise before it ever reaches the model - not just discourage the
    model from inventing a signal, but make it structurally impossible by never calling it."""
    provider = _FakeProvider(json.dumps({"signals": [{"signal": "fabricated", "strength": "high",
                                                       "evidence": "noise"}]}))
    request = IntentSignalRequest(
        requestId="r1", investorRef="inv-1",
        activity={"screens": {"Dashboard": 500}, "calculatorSteps": {}, "properties": []},
    )
    result = generate_intent_signals(request, provider)
    assert result is not None
    assert result.signals == []
    assert provider.calls == []


def test_generate_intent_signals_still_calls_the_llm_when_evidence_is_eligible():
    provider = _FakeProvider(json.dumps({
        "signals": [{"signal": "Interested in Manchester property", "strength": "high",
                    "evidence": "Manchester-area property viewed 5x"}],
    }))
    request = IntentSignalRequest(
        requestId="r1", investorRef="inv-1",
        activity={"screens": {}, "calculatorSteps": {},
                 "properties": [{"propertyName": "X", "location": "Manchester",
                                 "postcode": "M1 1AA", "visitCount": 5}]},
    )
    result = generate_intent_signals(request, provider)
    assert result is not None
    assert len(provider.calls) == 1
    assert result.signals[0].signal == "Interested in Manchester property"
