"""Port of app/Services/IdgSales/IdgSalesIngestFilter.php.

Applies the configured country + category allowlists to a normalized notice before it is
persisted as an Opportunity. Either allowlist can be disabled per-scan by passing the literal
string "*" for `country_allowlist` / `category_allowlist` in `scan_filters` (matches the PHP
`isAllowAll` escape hatch, used by e.g. the manual "scan everything" button).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.sales_intelligence.category_matcher import SecurityCategoryMatcher
from app.modules.sales_intelligence.target_countries import TargetCountries


@dataclass
class IngestFilter:
    target_countries: TargetCountries = field(default_factory=TargetCountries)
    security_matcher: SecurityCategoryMatcher = field(default_factory=SecurityCategoryMatcher)

    def _is_allow_all(self, scan_filters: dict, key: str) -> bool:
        value = scan_filters.get(key)
        if value is None:
            return False
        return str(value).strip() == "*"

    def evaluate(self, notice: dict, scan_filters: dict | None = None) -> dict:
        scan_filters = scan_filters or {}
        if not self._is_allow_all(scan_filters, "category_allowlist") and not self.security_matcher.matches(notice):
            return {"pass": False, "reason": "security_category"}
        if not self._is_allow_all(scan_filters, "country_allowlist"):
            country = str(notice.get("country") or "").strip()
            if not country or not self.target_countries.matches(country):
                return {"pass": False, "reason": "country"}
        return {"pass": True, "reason": None}

    def passes(self, notice: dict, scan_filters: dict | None = None) -> bool:
        return bool(self.evaluate(notice, scan_filters)["pass"])
