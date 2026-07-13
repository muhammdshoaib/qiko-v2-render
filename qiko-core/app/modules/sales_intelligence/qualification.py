"""Port of app/Services/IdgSales/IdgSalesQualificationService.php.

IMPORTANT DISCREPANCY vs. the task brief: this is a **deterministic, rule-based** bid/no-bid
scorer (keyword matching + country/buyer/value/deadline heuristics), NOT an LLM call. The real
branch never routes qualification through an LLM provider/gateway -- there is no prompt to port.
This module intentionally does *not* use app.modules.ai.gateway.LLMProvider, to stay faithful to
the real, working production logic. (A future LLM-assisted qualification pass could be layered on
top of this as an enhancement, but that would be new functionality, not a port.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.modules.sales_intelligence.target_countries import TargetCountries

SERVICE_KEYWORDS = (
    "security", "guarding", "guard", "protection", "risk", "safety", "access control",
    "perimeter", "surveillance", "cctv", "response", "k9",
)

TECHNOLOGY_KEYWORDS = ("software", "it", "computer", "technology", "digital", "cloud", "system", "network")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_until(deadline: datetime) -> int:
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (deadline - _now()).days


@dataclass
class QualificationService:
    target_countries: TargetCountries = field(default_factory=TargetCountries)

    def qualify(self, opportunity: dict) -> dict:
        title = str(opportunity.get("title") or "").lower()
        category = str(opportunity.get("category") or "").lower()
        country = str(opportunity.get("country") or "").lower()
        buyer = str(opportunity.get("buyer") or "")
        deadline = opportunity.get("deadline_at")

        score = 0
        reasons: list[str] = []
        risks: list[str] = []
        missing: list[str] = []

        service_score = self._service_alignment_score(f"{title} {category}")
        score += service_score
        if service_score >= 25:
            reasons.append("Tender language matches IDG security, guarding, protection, or risk services.")
        elif service_score > 0:
            reasons.append("Tender has partial service alignment but needs human confirmation.")
            risks.append("Service scope may be broader than IDG core security operations.")
        else:
            risks.append("No strong IDG security service keywords were found in the public notice.")

        if country:
            if self._country_looks_targeted(country):
                score += 18
                reasons.append("Beneficiary country appears to match an IDG target or active operating market.")
            else:
                score += 8
                risks.append("Beneficiary country needs IDG market fit review.")
        else:
            missing.append("country")

        if buyer:
            score += 12
            reasons.append("Buyer / contracting authority is available for source traceability.")
        else:
            missing.append("buyer")

        estimated_value = opportunity.get("estimated_value")
        if isinstance(estimated_value, (int, float)) and estimated_value > 0:
            score += 10
            reasons.append("Estimated contract value is present on the notice.")
        else:
            missing.append("estimated_value")
            risks.append("Public notice did not expose estimated contract value.")

        if isinstance(deadline, datetime):
            days = _days_until(deadline)
            if days >= 21:
                score += 15
                reasons.append("Submission window appears workable.")
            elif days >= 7:
                score += 10
                risks.append("Submission window is short and should be reviewed quickly.")
            elif days >= 0:
                score += 4
                risks.append("Deadline is urgent.")
            else:
                risks.append("Deadline appears to have passed.")
        else:
            missing.append("deadline")

        score = max(0, min(100, score))
        recommendation = self._recommendation(score, service_score, missing)
        dimensions = self._dimensions(title, category, country, estimated_value, deadline, service_score)
        stage = {"Bid": "qualified", "No Bid": "rejected"}.get(recommendation, "awaiting_review")

        return {
            "stage": stage,
            "recommendation": recommendation,
            "qualification_score": score,
            "confidence": self._confidence(missing),
            "competitor_readiness": "Medium" if score >= 75 else "Unknown",
            "qualification_summary": self._summary(recommendation, score, missing),
            "qualification_reasons": reasons,
            "qualification_dimensions": dimensions,
            "qualification_recommendations": self._recommendations(recommendation, missing, risks),
            "rejection_reasons": ["Low service alignment or low qualification score."] if recommendation == "No Bid" else [],
            "risks": list(dict.fromkeys(risks)),
            "missing_fields": list(dict.fromkeys(missing)),
        }

    def _dimensions(self, title: str, category: str, country: str, estimated_value, deadline, service_score: int) -> dict:
        service_match = min(100, round(service_score / 35 * 100))
        geography = 0
        if country:
            geography = 100 if self._country_looks_targeted(country) else 55
        industry = min(100, service_match + 10) if service_match > 0 else 20
        technology = self._technology_score(f"{title} {category}")
        security_clearance = 80 if "security" in f"{title} {category}" else 35
        framework = 60 if country else 25
        contract_value = 70 if isinstance(estimated_value, (int, float)) and estimated_value > 0 else 35

        deadline_score = 20
        if isinstance(deadline, datetime):
            days = _days_until(deadline)
            if days >= 21:
                deadline_score = 85
            elif days >= 7:
                deadline_score = 55
            elif days >= 0:
                deadline_score = 20
            else:
                deadline_score = 5

        strategic_customer = 75 if country and self._country_looks_targeted(country) else 40

        return {
            "serviceMatch": service_match, "geography": geography, "industry": min(100, industry),
            "technology": technology, "securityClearance": security_clearance, "framework": framework,
            "contractValue": contract_value, "deadline": deadline_score, "strategicCustomer": strategic_customer,
        }

    def _technology_score(self, text: str) -> int:
        matches = sum(1 for kw in TECHNOLOGY_KEYWORDS if kw in text)
        return min(100, matches * 25)

    def _recommendations(self, recommendation: str, missing: list[str], risks: list[str]) -> list[str]:
        items: list[str] = []
        if "estimated_value" in missing:
            items.append("Confirm contract value from the source notice or buyer clarification.")
        if "deadline" in missing:
            items.append("Verify submission deadline before committing bid resources.")
        if "country" in missing:
            items.append("Confirm beneficiary country and local delivery requirements.")
        if recommendation == "Review":
            items.append("Route to human review before approving pursuit.")
        if risks:
            items.append("Address flagged risks during bid/no-bid decision.")
        if not items:
            items.append("Proceed with standard opportunity review workflow.")
        return items

    def _service_alignment_score(self, text: str) -> int:
        matches = sum(1 for kw in SERVICE_KEYWORDS if kw in text)
        if matches >= 3:
            return 35
        if matches == 2:
            return 30
        if matches == 1:
            return 20
        return 0

    def _country_looks_targeted(self, country: str) -> bool:
        return self.target_countries.matches(country)

    def _recommendation(self, score: int, service_score: int, missing: list[str]) -> str:
        if service_score == 0 or score < 35:
            return "No Bid"
        if score >= 75 and len(set(missing)) <= 1:
            return "Bid"
        return "Review"

    def _confidence(self, missing: list[str]) -> int:
        return max(35, 85 - len(set(missing)) * 12)

    def _summary(self, recommendation: str, score: int, missing: list[str]) -> str:
        if recommendation == "Bid":
            return f"Auto-qualified with {score}% fit based on IDG service alignment and public notice metadata."
        if recommendation == "No Bid":
            return f"Rejected by initial qualification with {score}% fit. Human restoration is possible if context is missing."
        missing_text = "no mandatory fields missing" if not missing else "missing " + ", ".join(dict.fromkeys(missing))
        return f"Needs review with {score}% fit because the public notice is {missing_text}."
