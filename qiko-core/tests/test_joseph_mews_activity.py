import json

from app.modules.joseph_mews.activity import (
    ActivityEvent,
    IntentSignalRequest,
    aggregate_activity,
    generate_intent_signals,
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
    request = IntentSignalRequest(requestId="r1", investorRef="inv-1", activity={})
    result = generate_intent_signals(request, provider)
    assert result is not None
    assert result.signals[0].signal == "s"


def test_generate_intent_signals_returns_none_on_non_json():
    provider = _FakeProvider("not json at all")
    request = IntentSignalRequest(requestId="r1", investorRef="inv-1", activity={})
    assert generate_intent_signals(request, provider) is None


def test_generate_intent_signals_returns_none_when_provider_raises():
    class _RaisingProvider:
        def generate(self, *a, **k):
            raise AttributeError("network is down")

    request = IntentSignalRequest(requestId="r1", investorRef="inv-1", activity={})
    assert generate_intent_signals(request, _RaisingProvider()) is None


def test_generate_intent_signals_with_no_signals_returns_empty_list_not_none():
    provider = _FakeProvider(json.dumps({"signals": []}))
    request = IntentSignalRequest(requestId="r1", investorRef="inv-1", activity={})
    result = generate_intent_signals(request, provider)
    assert result is not None
    assert result.signals == []
