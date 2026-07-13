"""Port of app/Services/IdgSales/IdgSalesTargetCountries.php.

KNOWN GAP IN THE SOURCE BRANCH: `IdgSalesTargetCountries::all()` reads `config('idg_sales.target_countries', [])`,
but `config/idg_sales.php` on `origin/idg-sales` only defines `scan_interval_minutes` -- the
`target_countries` key is never populated anywhere in the branch (grep confirms no other file
sets it), so in production that class always returns `[]` and `matches()` always returns False
unless it is set via an uncommitted `.env`/runtime config. This is a real discrepancy between the
"14-country IDG allowlist" referenced in the product brief and what actually ships in the
branch's committed code.

DEFAULT_TARGET_COUNTRIES below is Qiko's own reasonable placeholder (IDG's core GCC + East
Africa/Horn of Africa security markets, inferred from the non-EU/EEA countries
`TedCountryResolver::ALPHA3_TO_ALPHA2` was deliberately extended with: IRQ, ARE, SOM, KEN, UGA,
SSD, AFG). Confirm the authoritative 14-country list with product/IDG before relying on this in
production -- override via `IDG_SALES_TARGET_COUNTRIES` (comma-separated country names) if needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_TARGET_COUNTRIES: list[dict] = [
    {"code": "AE", "name": "United Arab Emirates", "aliases": ["united arab emirates", "uae"]},
    {"code": "SA", "name": "Saudi Arabia", "aliases": ["saudi arabia", "ksa"]},
    {"code": "QA", "name": "Qatar", "aliases": ["qatar"]},
    {"code": "KW", "name": "Kuwait", "aliases": ["kuwait"]},
    {"code": "BH", "name": "Bahrain", "aliases": ["bahrain"]},
    {"code": "OM", "name": "Oman", "aliases": ["oman"]},
    {"code": "JO", "name": "Jordan", "aliases": ["jordan"]},
    {"code": "IQ", "name": "Iraq", "aliases": ["iraq"]},
    {"code": "YE", "name": "Yemen", "aliases": ["yemen"]},
    {"code": "SO", "name": "Somalia", "aliases": ["somalia"]},
    {"code": "KE", "name": "Kenya", "aliases": ["kenya"]},
    {"code": "UG", "name": "Uganda", "aliases": ["uganda"]},
    {"code": "SS", "name": "South Sudan", "aliases": ["south sudan"]},
    {"code": "AF", "name": "Afghanistan", "aliases": ["afghanistan"]},
]


def _normalize(value: str) -> str:
    return (value or "").strip().lower()


@dataclass
class TargetCountries:
    countries: list[dict] = field(default_factory=lambda: list(DEFAULT_TARGET_COUNTRIES))

    def all(self) -> list[dict]:
        return list(self.countries)

    def all_aliases(self) -> list[str]:
        aliases: list[str] = []
        for country in self.countries:
            for alias in country.get("aliases", []):
                normalized = _normalize(str(alias))
                if normalized and normalized not in aliases:
                    aliases.append(normalized)
        return aliases

    def matches(self, country: str | None) -> bool:
        normalized = _normalize(str(country or ""))
        if not normalized:
            return False
        segments = re.split(r"[,;|/]+", normalized) or [normalized]
        aliases = self.all_aliases()
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            for alias in aliases:
                if alias in segment:
                    return True
        return False
