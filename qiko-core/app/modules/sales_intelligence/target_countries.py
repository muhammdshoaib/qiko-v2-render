"""Target-country allowlist for opportunity qualification.

This is now config-driven per agent: the qualification scorer builds its `TargetCountries` from
the agent's own `config.si_target_countries` (a list of country names/aliases, or full
{code,name,aliases} dicts) via `TargetCountries.from_config`. When an agent sets nothing, we fall
back to DEFAULT_TARGET_COUNTRIES so existing (IDG) behaviour is unchanged.

DEFAULT_TARGET_COUNTRIES is IDG's core GCC + East Africa/Horn of Africa security markets (the
non-EU/EEA countries `TedCountryResolver::ALPHA3_TO_ALPHA2` was extended with: IRQ, ARE, SOM, KEN,
UGA, SSD, AFG). Non-security tenants override it per agent through `si_target_countries`.
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

    @classmethod
    def from_config(cls, value, default: "TargetCountries | None" = None) -> "TargetCountries":
        """Build from an agent-config `si_target_countries` value. Accepts a list of country
        names/aliases (strings) or full {code, name, aliases} dicts. Falls back to `default`
        (or the IDG GCC default) when the value is missing, empty, or not a list."""
        fallback = default if default is not None else cls()
        if not isinstance(value, list) or not value:
            return fallback

        countries: list[dict] = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                aliases = [str(a) for a in (item.get("aliases") or []) if str(a).strip()]
                if name and name.lower() not in [a.lower() for a in aliases]:
                    aliases = [name, *aliases]
                if not name and not aliases:
                    continue
                countries.append({"code": str(item.get("code") or ""), "name": name, "aliases": aliases})
            else:
                name = str(item).strip()
                if not name:
                    continue
                countries.append({"code": "", "name": name, "aliases": [name]})

        return cls(countries=countries) if countries else fallback

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
