"""Lead qualification scoring for Joe's WhatsApp flow (JM2-1029/1030).

Confirmed against the shared Miro flow board ("Joseph Mews - WhatsApp Bot", both the Inbound and
Outbound Layer frames use the identical shape: qualify -> calculate score -> route outcome) and
the client's own prompt ("JOE - Custom prompt.pdf", Stage 3's 4 qualification criteria). Both
sources agree on the scoring INPUTS (timeline, budget, journey stage, funding, interest, other
factors) and the four possible outcomes (nurture / escalate / webinar / meeting), but neither
specifies the actual point weights or threshold, so those are not on the board or in the prompt to
read off. The weights below are a deliberately simple, documented starting point (not invented
business logic dressed up as confirmed), meant to be tuned in one place once Razvan/the client
confirm real weights, not a design that needs revisiting to change them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Timeline(str, Enum):
    soon = "soon"  # "next few months / ASAP", the prompt's HIGH_INTENT bucket
    future = "future"  # "planning / researching / next year", the prompt's FUTURE_INTENT bucket
    unknown = "unknown"


class FundingMethod(str, Enum):
    cash = "cash"
    mortgage = "mortgage"
    unknown = "unknown"


class RouteOutcome(str, Enum):
    nurture = "nurture"
    escalate = "escalate"
    webinar = "webinar"
    meeting = "meeting"


# Deliberately a plain module-level constant, not buried in a method, so it is the one place to
# change once real weights are confirmed.
DEFAULT_THRESHOLD = 60


@dataclass(frozen=True)
class LeadQualification:
    """What Joe has gathered about a lead by the time scoring runs. All fields are optional
    because scoring can run on a partial conversation (e.g. a lead who goes quiet mid-flow)."""

    timeline: Timeline = Timeline.unknown
    has_budget_signal: bool = False  # mentioned a number, a range, or "cash ready" etc.
    funding_method: FundingMethod = FundingMethod.unknown
    journey_stage: str = ""  # e.g. "first_time", "experienced" -- free text, not yet enumerated
    interest_signal: bool = False  # asked a specific/technical question, named a location, etc.
    wants_human: bool = False  # explicit escalation trigger from the prompt's escalation protocol
    other_factors: int = 0  # any additional positive signals not captured above, each worth 1 point


def score(qualification: LeadQualification) -> int:
    """0-100ish points, higher = more ready to book now. See module docstring: weights are a
    starting point, not a confirmed formula."""
    points = 0
    if qualification.timeline is Timeline.soon:
        points += 40
    elif qualification.timeline is Timeline.future:
        points += 10
    if qualification.has_budget_signal:
        points += 20
    if qualification.funding_method is not FundingMethod.unknown:
        points += 10
    if qualification.interest_signal:
        points += 15
    points += min(qualification.other_factors, 3) * 5
    return points


def route_outcome(qualification: LeadQualification, *, threshold: int = DEFAULT_THRESHOLD) -> RouteOutcome:
    """Matches the Miro board's "Route outcome" diamond: escalate takes priority over everything
    (the prompt's escalation protocol is explicit that a human ask always wins), then above/below
    threshold decides meeting vs continued nurture, and an unknown timeline with no other signal
    falls back to sharing webinar info rather than either extreme."""
    if qualification.wants_human:
        return RouteOutcome.escalate
    if score(qualification) >= threshold:
        return RouteOutcome.meeting
    if qualification.timeline is Timeline.unknown and not qualification.interest_signal:
        return RouteOutcome.webinar
    return RouteOutcome.nurture
