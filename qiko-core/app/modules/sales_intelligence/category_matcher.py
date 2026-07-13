"""Port of app/Services/IdgSales/IdgSalesSecurityCategoryMatcher.php.

Same config gap noted in target_countries.py applies here: `config('idg_sales.category_allowlist')`
and `config('idg_sales.security_category.*')` are read by the PHP but never populated in
`config/idg_sales.php` on the branch. DEFAULT_CATEGORY_ALLOWLIST / CPV_PREFIXES / BUNDLE_REJECT_PATTERNS
below are Qiko's own reasonable defaults for IDG's security/guarding vertical -- confirm with
product before relying on this in production.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# CPV 7971xxxx = "Security services" in the EU Common Procurement Vocabulary.
DEFAULT_CPV_PREFIXES: list[str] = ["7971"]

DEFAULT_CATEGORY_ALLOWLIST: list[dict] = [
    {"key": "security_services", "aliases": [
        "security services", "guarding services", "security guarding", "static security",
        "manned guarding", "close protection", "risk management services", "safety and security",
        "access control", "perimeter security", "surveillance services", "cctv monitoring",
        "k9 detection", "explosive detection", "security consultancy",
    ]},
]

DEFAULT_BUNDLE_REJECT_PATTERNS: list[str] = [
    "facilities management and security",
    "cleaning and security services",
    "catering and security",
]


def _clean(value: str) -> str:
    return (value or "").strip().lower()


@dataclass
class SecurityCategoryMatcher:
    category_allowlist: list[dict] = field(default_factory=lambda: list(DEFAULT_CATEGORY_ALLOWLIST))
    cpv_prefixes: list[str] = field(default_factory=lambda: list(DEFAULT_CPV_PREFIXES))
    bundle_reject_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_BUNDLE_REJECT_PATTERNS))

    def _category_aliases(self) -> list[str]:
        aliases: list[str] = []
        for group in self.category_allowlist:
            for alias in group.get("aliases", []):
                normalized = _clean(str(alias))
                if normalized and normalized not in aliases:
                    aliases.append(normalized)
        aliases.sort(key=len, reverse=True)
        return aliases

    def _looks_like_bundled_business_services(self, text: str) -> bool:
        return any(_clean(p) in text for p in self.bundle_reject_patterns)

    def _has_security_cpv(self, notice: dict) -> bool:
        raw = notice.get("raw") if isinstance(notice.get("raw"), dict) else {}
        candidates = [raw.get("classification-cpv"), raw.get("main-classification-proc")]
        for candidate in candidates:
            digits = re.sub(r"\D+", "", _first_scalar(candidate))
            if not digits:
                continue
            if any(digits.startswith(p) for p in self.cpv_prefixes):
                return True
        category = str(notice.get("category") or "")
        m = re.search(r"cpv\s*(\d+)", category, re.IGNORECASE)
        if m and any(m.group(1).startswith(p) for p in self.cpv_prefixes):
            return True
        return False

    def matches(self, notice: dict) -> bool:
        category = _clean(str(notice.get("category") or ""))
        title = _clean(str(notice.get("title") or ""))
        description = _clean(str(notice.get("description") or ""))
        combined = " ".join(x for x in (title, category, description) if x).strip()
        if not combined:
            return False
        if self._looks_like_bundled_business_services(combined):
            return False
        if self._has_security_cpv(notice):
            return True
        aliases = self._category_aliases()
        if not aliases:
            return False
        for text in (category, title, description):
            if text and any(alias in text for alias in aliases):
                return True
        return False


def _first_scalar(value) -> str:
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, list) and value:
        return _first_scalar(value[0])
    return ""
