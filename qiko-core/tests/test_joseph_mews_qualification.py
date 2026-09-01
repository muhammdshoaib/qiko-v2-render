from app.modules.joseph_mews.qualification import (
    DEFAULT_THRESHOLD,
    FundingMethod,
    LeadQualification,
    RouteOutcome,
    Timeline,
    route_outcome,
    score,
)


def test_score_is_zero_for_a_fully_unknown_lead():
    assert score(LeadQualification()) == 0


def test_soon_timeline_scores_higher_than_future_timeline():
    soon = score(LeadQualification(timeline=Timeline.soon))
    future = score(LeadQualification(timeline=Timeline.future))
    assert soon > future > 0


def test_budget_and_funding_and_interest_signals_all_add_points():
    base = score(LeadQualification())
    assert score(LeadQualification(has_budget_signal=True)) > base
    assert score(LeadQualification(funding_method=FundingMethod.cash)) > base
    assert score(LeadQualification(interest_signal=True)) > base


def test_other_factors_are_capped_so_a_noisy_conversation_cannot_dominate_the_score():
    capped = score(LeadQualification(other_factors=3))
    uncapped_attempt = score(LeadQualification(other_factors=50))
    assert capped == uncapped_attempt


def test_wants_human_always_escalates_regardless_of_score():
    high_scoring_but_escalating = LeadQualification(
        timeline=Timeline.soon, has_budget_signal=True, interest_signal=True, wants_human=True
    )
    assert route_outcome(high_scoring_but_escalating) is RouteOutcome.escalate


def test_a_high_score_routes_to_meeting():
    ready = LeadQualification(
        timeline=Timeline.soon, has_budget_signal=True, funding_method=FundingMethod.cash,
        interest_signal=True,
    )
    assert score(ready) >= DEFAULT_THRESHOLD
    assert route_outcome(ready) is RouteOutcome.meeting


def test_a_fully_unknown_lead_with_no_interest_signal_gets_webinar_info():
    assert route_outcome(LeadQualification()) is RouteOutcome.webinar


def test_a_below_threshold_lead_with_some_signal_gets_nurtured():
    some_signal = LeadQualification(timeline=Timeline.future, interest_signal=True)
    assert score(some_signal) < DEFAULT_THRESHOLD
    assert route_outcome(some_signal) is RouteOutcome.nurture


def test_threshold_is_overridable_without_changing_the_scoring_formula():
    mid = LeadQualification(timeline=Timeline.future, has_budget_signal=True)
    assert route_outcome(mid, threshold=100) is not RouteOutcome.meeting
    assert route_outcome(mid, threshold=1) is RouteOutcome.meeting
