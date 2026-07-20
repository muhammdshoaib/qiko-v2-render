"""Port of app/Services/IdgSales/IdgSalesOpportunityDetailService.php: builds the rich "detail"
block embedded in the opportunity resource (overview/summary/qualification/completed/notes tabs
in the Studio UI)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.sales_intelligence.connectors import UngmNoticeConnector
from app.modules.sales_intelligence.models import Opportunity

_DURATION_UNIT_MAP = {"MONTH": "month", "YEAR": "year", "ANN": "year", "DAY": "day", "WEEK": "week"}


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _first_raw_scalar(raw: dict, keys: list[str]) -> str | None:
    for key in keys:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str) and first:
                return first
            if isinstance(first, (int, float)):
                return str(first)
    return None


def _flatten_raw_scalars(value) -> list[str]:
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_flatten_raw_scalars(item))
        return items
    return []


def _raw_scalars(raw: dict, keys: list[str]) -> list[str]:
    for key in keys:
        if key not in raw:
            continue
        values = _flatten_raw_scalars(raw[key])
        if values:
            return values
    return []


@dataclass
class OpportunityDetailService:
    ungm: UngmNoticeConnector = field(default_factory=UngmNoticeConnector)

    def build(self, opportunity: Opportunity) -> dict:
        dimensions = opportunity.qualification_dimensions or {}
        raw = self._resolve_raw_payload(opportunity)
        # Manually-entered opportunities carry their richer fields in raw_payload["manual"]; overlay
        # them on top of the source-derived sections so the detail tabs show what the operator typed.
        manual = raw.get("manual") if isinstance(raw.get("manual"), dict) else {}
        return {
            "overview": self._overview(opportunity, raw, manual),
            "summary": self._summary(opportunity, raw, manual),
            "qualification": self._qualification(opportunity, dimensions, manual),
            "completed": self._completed(opportunity),
            "notes": self._notes(opportunity),
        }

    def _resolve_raw_payload(self, opportunity: Opportunity) -> dict:
        raw = opportunity.raw_payload or {}
        if opportunity.source_key != "ungm":
            return raw
        if self._ungm_detail(raw):
            return raw
        notice_id = self._ungm_notice_id(raw, opportunity)
        if not notice_id:
            return raw
        detail = self.ungm.fetch_detail(notice_id)
        if not detail:
            return raw
        return {"search": self._ungm_search(raw), "detail": detail}

    def _overview(self, opportunity: Opportunity, raw: dict, manual: dict | None = None) -> dict:
        if opportunity.source_key == "ungm":
            source_fields = self._extract_ungm_overview_fields(raw)
        elif opportunity.source_key == "ted":
            source_fields = self._extract_ted_overview_fields(raw)
        else:
            source_fields = self._extract_generic_overview_fields(raw)

        base = {
            "deadlineAt": _iso(opportunity.deadline_at),
            "estimatedValue": float(opportunity.estimated_value) if opportunity.estimated_value is not None else None,
            "currency": opportunity.currency,
            "country": self._resolve_country(opportunity, raw),
            "category": opportunity.category,
            "buyer": opportunity.buyer,
            "source": opportunity.source_name,
            "sourceUrl": opportunity.source_url,
            "publishedAt": _iso(opportunity.published_at),
            "extractionConfidence": opportunity.confidence,
        }
        base.update(source_fields)
        base["technology"] = source_fields.get("technology") or opportunity.category
        self._apply_manual_overview(base, manual or {})
        return base

    def _apply_manual_overview(self, base: dict, manual: dict) -> None:
        """Overlay operator-entered overview fields (Ali's Overview tab) onto the source-derived base."""
        for camel, key in (("reference", "reference"), ("noticeType", "notice_type"),
                           ("securityClearance", "security_clearance"), ("framework", "framework"),
                           ("contractDuration", "contract_duration"), ("technology", "technology")):
            if manual.get(key) not in (None, ""):
                base[camel] = manual[key]
        if manual.get("contacts"):
            base["contacts"] = manual["contacts"]
        if manual.get("links"):
            base["links"] = manual["links"]
        if manual.get("extraction_confidence") is not None:
            base["extractionConfidence"] = manual["extraction_confidence"]

    def _summary(self, opportunity: Opportunity, raw: dict, manual: dict | None = None) -> dict:
        risks = opportunity.risks or []
        reasons = opportunity.qualification_reasons or []
        description = self._notice_description(raw)
        result = {
            "executiveSummary": self._executive_summary(opportunity, description, self._resolve_country(opportunity, raw)),
            "riskSummary": " ".join(risks) if risks else "No major risks flagged during initial qualification.",
            "opportunitySummary": self._opportunity_summary(opportunity),
            "requirements": reasons or ([description] if description else
                                        ["Review the source notice for full scope and compliance requirements."]),
            "deliverables": self._deliverables(opportunity, raw),
        }
        manual = manual or {}
        for camel, key in (("executiveSummary", "executive_summary"), ("riskSummary", "risk_summary"),
                           ("opportunitySummary", "opportunity_summary")):
            if manual.get(key) not in (None, ""):
                result[camel] = manual[key]
        if manual.get("requirements"):
            result["requirements"] = manual["requirements"]
        if manual.get("deliverables"):
            result["deliverables"] = manual["deliverables"]
        return result

    def _qualification(self, opportunity: Opportunity, dimensions: dict, manual: dict | None = None) -> dict:
        manual = manual or {}
        return {
            "overallScore": opportunity.qualification_score,
            "recommendation": opportunity.recommendation,
            "confidence": opportunity.confidence,
            "dimensions": dimensions,
            "aiReasoning": manual.get("ai_reasoning") or opportunity.qualification_summary,
            "recommendations": manual.get("recommendations") or opportunity.qualification_recommendations or [],
            "reasons": opportunity.qualification_reasons or [],
            "risks": opportunity.risks or [],
            "rejectionReasons": opportunity.rejection_reasons or [],
        }

    def _completed(self, opportunity: Opportunity) -> dict:
        is_complete = opportunity.stage in ("pushed", "rejected", "validated", "push_failed")
        return {
            "isComplete": is_complete, "stage": opportunity.stage,
            "humanReviewStatus": opportunity.human_review_status,
            "reviewedBy": {"id": opportunity.reviewed_by_user_id} if opportunity.reviewed_by_user_id else None,
            "reviewedAt": _iso(opportunity.reviewed_at),
            "salesforcePushStatus": opportunity.salesforce_push_status,
            "salesforceOpportunityId": opportunity.salesforce_opportunity_id,
            "salesforcePushedAt": _iso(opportunity.salesforce_pushed_at),
            "salesforcePushError": opportunity.salesforce_push_error,
            "completedAt": self._completed_at(opportunity),
        }

    def _notes(self, opportunity: Opportunity) -> dict:
        return {"humanReviewNotes": opportunity.human_review_notes, "updatedAt": _iso(opportunity.updated_at)}

    def _extract_ted_overview_fields(self, raw: dict) -> dict:
        cpv = _first_raw_scalar(raw, ["classification-cpv", "main-classification-proc"])
        return {"securityClearance": None, "contacts": self._extract_ted_contacts(raw), "framework": None,
                "contractDuration": self._extract_contract_duration(raw), "technology": cpv or None}

    def _extract_ungm_overview_fields(self, raw: dict) -> dict:
        detail = self._ungm_detail(raw)
        unspsc = detail.get("unspsc") or []
        technology = None
        if unspsc:
            first = unspsc[0]
            technology = f"{first.get('code', '')} {first.get('title', '')}".strip() if isinstance(first, dict) else None
        search = self._ungm_search(raw)
        return {
            "securityClearance": None, "contacts": self._extract_ungm_contacts(detail), "framework": None,
            "contractDuration": None, "technology": technology or None,
            "reference": detail.get("reference") or search.get("reference"),
            "noticeType": detail.get("notice_type") or search.get("notice_type"),
            "links": detail.get("links") or [],
        }

    def _extract_generic_overview_fields(self, raw: dict) -> dict:
        ted_contacts = self._extract_ted_contacts(raw)
        ungm_contacts = self._extract_ungm_contacts(self._ungm_detail(raw))
        return {"securityClearance": None, "contacts": ted_contacts or ungm_contacts, "framework": None,
                "contractDuration": self._extract_contract_duration(raw),
                "technology": _first_raw_scalar(raw, ["classification-cpv", "main-classification-proc"])}

    def _extract_ungm_contacts(self, detail: dict) -> list[dict]:
        normalized = []
        for contact in detail.get("contacts") or []:
            if not isinstance(contact, dict):
                continue
            name = str(contact.get("name") or "").strip()
            email = str(contact.get("email") or "").strip()
            phone = str(contact.get("phone") or "").strip()
            if not name and not email and not phone:
                continue
            normalized.append({"name": name or None, "email": email or None, "phone": phone or None})
        return normalized

    def _executive_summary(self, opportunity: Opportunity, description: str | None, country: str | None) -> str:
        buyer = opportunity.buyer or "the contracting authority"
        country = country or opportunity.country or "the listed market"
        category = opportunity.category or "the published scope"
        tail = description or opportunity.qualification_summary or "Initial extraction completed from the public notice."
        return f"Procurement opportunity from {buyer} in {country} for {category}. {tail}"

    def _opportunity_summary(self, opportunity: Opportunity) -> str:
        if opportunity.qualification_score is None:
            return "Opportunity ingested and awaiting qualification."
        recommendation = opportunity.recommendation or "Review"
        return (f"Current recommendation is {recommendation} with a {opportunity.qualification_score}/100 "
                "qualification score based on IDG service fit and notice metadata.")

    def _deliverables(self, opportunity: Opportunity, raw: dict) -> list[str]:
        items: list[str] = []
        detail = self._ungm_detail(raw)
        for entry in detail.get("unspsc") or []:
            if isinstance(entry, dict) and entry.get("title"):
                items.append(entry["title"].strip())
        category = (opportunity.category or "").lower()
        if "security" in category:
            items.append("Security and guarding services")
        if "service" in category:
            items.append("Professional services delivery")
        if not items and opportunity.category:
            items.append(opportunity.category)
        if not items:
            items.append("Scope to be confirmed from source notice")
        return list(dict.fromkeys(items))

    def _completed_at(self, opportunity: Opportunity) -> str | None:
        if opportunity.salesforce_pushed_at:
            return _iso(opportunity.salesforce_pushed_at)
        if opportunity.reviewed_at and opportunity.stage in ("rejected", "validated"):
            return _iso(opportunity.reviewed_at)
        return None

    def _notice_description(self, raw: dict) -> str | None:
        description = str(self._ungm_detail(raw).get("description") or "").strip()
        return description or None

    def _ungm_detail(self, raw: dict) -> dict:
        detail = raw.get("detail")
        return detail if isinstance(detail, dict) else {}

    def _ungm_search(self, raw: dict) -> dict:
        search = raw.get("search")
        return search if isinstance(search, dict) else raw

    def _ungm_notice_id(self, raw: dict, opportunity: Opportunity) -> str:
        return str(self._ungm_search(raw).get("notice_id") or opportunity.external_id or "").strip()

    def _resolve_country(self, opportunity: Opportunity, raw: dict) -> str | None:
        if opportunity.source_key == "ungm":
            beneficiary = str(self._ungm_detail(raw).get("beneficiary_countries") or "").strip()
            if beneficiary:
                return beneficiary
        country = (opportunity.country or "").strip()
        return country or None

    def _extract_ted_contacts(self, raw: dict) -> list[dict]:
        names = _raw_scalars(raw, ["buyer-contact-point"])
        emails = list(dict.fromkeys(_raw_scalars(raw, ["buyer-email", "organisation-email-buyer"])))
        phones = list(dict.fromkeys(_raw_scalars(raw, ["organisation-tel-buyer", "organisation-tel-tender-receip-lot"])))
        count = max(len(names), len(emails), len(phones))
        contacts = []
        for i in range(count):
            contact = {"name": names[i] if i < len(names) else None,
                       "email": emails[i] if i < len(emails) else None,
                       "phone": phones[i] if i < len(phones) else None}
            if any(contact.values()):
                contacts.append(contact)
        return contacts

    def _extract_contract_duration(self, raw: dict) -> str | None:
        periods = []
        items = raw.get("contract-duration-period-lot")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                value = str(item.get("value") or "").strip()
                unit = str(item.get("unit") or "").strip()
                if value and unit:
                    periods.append(self._format_duration(value, unit))
        if not periods:
            values = _raw_scalars(raw, ["duration-period-value-lot"])
            units = _raw_scalars(raw, ["duration-period-unit-lot"])
            for i in range(max(len(values), len(units))):
                value = values[i] if i < len(values) else ""
                unit = units[i] if i < len(units) else ""
                if value and unit:
                    periods.append(self._format_duration(value, unit))
        periods = list(dict.fromkeys(periods))
        if not periods:
            return None
        return periods[0] if len(periods) == 1 else ", ".join(periods)

    def _format_duration(self, value: str, unit: str) -> str:
        normalized_unit = _DURATION_UNIT_MAP.get(unit.upper(), unit.lower())
        try:
            is_one = int(value) == 1
        except ValueError:
            is_one = False
        if not is_one and not normalized_unit.endswith("s"):
            normalized_unit += "s"
        return f"{value} {normalized_unit}".strip()
