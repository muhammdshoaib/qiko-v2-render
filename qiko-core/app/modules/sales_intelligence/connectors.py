"""Real TED (EU Tenders Electronic Daily) + UNGM (UN Global Marketplace) connectors.

Faithful port of:
 - app/Services/IdgSales/Connectors/TedCountryResolver.php
 - app/Services/IdgSales/Connectors/TedNoticeConnector.php
 - app/Services/IdgSales/Connectors/UngmNoticeConnector.php
 - app/Services/IdgSales/Connectors/UngmNoticeDetailParser.php

Both connectors hit fixed, hardcoded base hosts (ted.europa.eu / ungm.org) -- never derived from
request/user input, so there is no SSRF surface here. HTTP calls use a short (30-45s) timeout,
mirroring the PHP `Http::timeout(...)`.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse

import httpx
from lxml import etree as lxml_etree
from lxml import html as lxml_html

from app.modules.sales_intelligence.ingest_filter import IngestFilter
from app.modules.sales_intelligence.ssrf import SsrfError, assert_public_url

_WHITESPACE_RE = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", html.unescape(value or "")).strip()


# ISO 3166-1 alpha-3 -> alpha-2 (EU/EEA + common TED publishing countries).
ALPHA3_TO_ALPHA2 = {
    "ALB": "AL", "AND": "AD", "AUT": "AT", "BEL": "BE", "BGR": "BG", "BIH": "BA", "CHE": "CH",
    "CYP": "CY", "CZE": "CZ", "DEU": "DE", "DNK": "DK", "ESP": "ES", "EST": "EE", "FIN": "FI",
    "FRA": "FR", "GBR": "GB", "GRC": "GR", "HRV": "HR", "HUN": "HU", "IRL": "IE", "ISL": "IS",
    "ITA": "IT", "LIE": "LI", "LTU": "LT", "LUX": "LU", "LVA": "LV", "MKD": "MK", "MLT": "MT",
    "MNE": "ME", "NLD": "NL", "NOR": "NO", "POL": "PL", "PRT": "PT", "ROU": "RO", "SRB": "RS",
    "SVK": "SK", "SVN": "SI", "SWE": "SE", "TUR": "TR", "UKR": "UA", "USA": "US", "CAN": "CA",
    "AUS": "AU", "JPN": "JP", "KOR": "KR", "IND": "IN", "ZAF": "ZA", "BRA": "BR", "MEX": "MX",
    "CHN": "CN", "IRQ": "IQ", "ARE": "AE", "SOM": "SO", "KEN": "KE", "UGA": "UG", "SSD": "SS",
    "AFG": "AF", "NPL": "NP", "MMR": "MM", "MYS": "MY", "XKX": "XK",
}

# Minimal alpha-2 -> English display name fallback (Python has no bundled ICU/Locale like PHP's
# \Locale::getDisplayRegion; a real deployment can use `pycountry` if richer coverage is needed).
_ALPHA2_NAMES = {
    "AL": "Albania", "AD": "Andorra", "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria",
    "BA": "Bosnia and Herzegovina", "CH": "Switzerland", "CY": "Cyprus", "CZ": "Czechia",
    "DE": "Germany", "DK": "Denmark", "ES": "Spain", "EE": "Estonia", "FI": "Finland",
    "FR": "France", "GB": "United Kingdom", "GR": "Greece", "HR": "Croatia", "HU": "Hungary",
    "IE": "Ireland", "IS": "Iceland", "IT": "Italy", "LI": "Liechtenstein", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "MK": "North Macedonia", "MT": "Malta",
    "ME": "Montenegro", "NL": "Netherlands", "NO": "Norway", "PL": "Poland", "PT": "Portugal",
    "RO": "Romania", "RS": "Serbia", "SK": "Slovakia", "SI": "Slovenia", "SE": "Sweden",
    "TR": "Turkey", "UA": "Ukraine", "US": "United States", "CA": "Canada", "AU": "Australia",
    "JP": "Japan", "KR": "South Korea", "IN": "India", "ZA": "South Africa", "BR": "Brazil",
    "MX": "Mexico", "CN": "China", "IQ": "Iraq", "AE": "United Arab Emirates", "SO": "Somalia",
    "KE": "Kenya", "UG": "Uganda", "SS": "South Sudan", "AF": "Afghanistan", "NP": "Nepal",
    "MM": "Myanmar", "MY": "Malaysia", "XK": "Kosovo",
}


class TedCountryResolver:
    """Resolves TED place-of-performance codes (ISO/NUTS) to English country names."""

    def resolve_from_codes(self, codes: list[str]) -> str:
        normalized = list(dict.fromkeys(c.strip().upper() for c in codes if str(c).strip()))
        for code in normalized:
            if re.fullmatch(r"[A-Z]{3}", code) and code in ALPHA3_TO_ALPHA2:
                name = self.country_name_from_alpha2(ALPHA3_TO_ALPHA2[code])
                if name:
                    return name
        for code in normalized:
            if re.fullmatch(r"[A-Z]{2}", code):
                name = self.country_name_from_alpha2(code)
                if name:
                    return name
            m = re.match(r"^([A-Z]{2})\d", code)
            if m:
                name = self.country_name_from_alpha2(m.group(1))
                if name:
                    return name
        return ""

    def country_name_from_alpha2(self, alpha2: str) -> str:
        alpha2 = alpha2.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", alpha2):
            return ""
        return _ALPHA2_NAMES.get(alpha2, "")


TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
TED_FIELDS = [
    "publication-number", "notice-title", "buyer-name", "buyer-contact-point", "buyer-email",
    "organisation-email-buyer", "organisation-tel-buyer", "deadline-receipt-tender-date-lot",
    "publication-date", "classification-cpv", "main-classification-proc",
    "contract-nature-main-proc", "estimated-value-proc", "estimated-value-cur-proc",
    "place-of-performance", "notice-type", "duration-period-value-lot",
    "duration-period-unit-lot", "contract-duration-period-lot", "links",
]


def _first_scalar(value) -> str:
    if isinstance(value, (str, int, float)):
        return _clean_text(str(value))
    if isinstance(value, list) and value:
        return _first_scalar(value[0])
    return ""


def _collect_scalars(value) -> list[str]:
    if isinstance(value, (str, int, float)):
        text = _clean_text(str(value))
        return [text] if text else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_collect_scalars(item))
        return items
    return []


def _localized_text(value) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        for lang in ("eng", "en", "ENG", "EN"):
            if value.get(lang):
                candidate = value[lang][0] if isinstance(value[lang], list) else value[lang]
                text = _clean_text(str(candidate))
                if text:
                    return text
        for item in value.values():
            text = _localized_text(item)
            if text:
                return text
    return ""


def _parse_ted_date(value: str | None) -> datetime | None:
    value = _clean_text(str(value or ""))
    if not value:
        return None
    try:
        from dateutil import parser as dateutil_parser

        dt = dateutil_parser.parse(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@dataclass
class TedNoticeConnector:
    country_resolver: TedCountryResolver = field(default_factory=TedCountryResolver)
    ingest_filter: IngestFilter = field(default_factory=IngestFilter)
    client: httpx.Client | None = None

    def _http(self) -> httpx.Client:
        return self.client or httpx.Client(timeout=45.0)

    def search(self, filters: dict | None = None) -> dict:
        filters = filters or {}
        payload = self._build_payload(filters)
        c = self._http()
        response = c.post(TED_SEARCH_URL, json=payload,
                          headers={"Accept": "application/json",
                                   "User-Agent": "Qiko IDG Sales Intelligence Worker/1.0"})
        if response.status_code >= 400:
            try:
                message = response.json().get("message")
            except Exception:
                message = response.text
            raise RuntimeError(f"TED search failed with status {response.status_code}: {str(message)[:300]}")

        body = response.json() if response.content else {}
        raw_notices = body.get("notices") or []
        skipped = 0
        notices = []
        for raw_notice in raw_notices:
            normalized = self._normalize_notice(raw_notice if isinstance(raw_notice, dict) else {})
            if normalized is None:
                continue
            if not self.ingest_filter.passes(normalized, filters):
                skipped += 1
                continue
            notices.append(normalized)

        return {
            "payload": payload,
            "total_notice_count": int(body.get("totalNoticeCount", len(raw_notices))),
            "notices": notices,
            "skipped": skipped,
        }

    def _build_payload(self, filters: dict) -> dict:
        limit = max(1, min(50, int(filters.get("page_size") or filters.get("limit") or 10)))
        query = str(filters.get("query") or "").strip()
        published_from = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y%m%d")
        expert_query = f"publication-date>={published_from}"

        if query:
            token = self._escape_expert_token(query)
            if token:
                expert_query += f" AND notice-title~{token}"
        if filters.get("title"):
            expert_query += f" AND notice-title~{self._escape_expert_token(str(filters['title']))}"

        return {
            "query": expert_query, "fields": TED_FIELDS, "limit": limit, "scope": "ACTIVE",
            "paginationMode": "PAGE_NUMBER", "page": max(1, int(filters.get("page_index") or 0) + 1),
            "checkQuerySyntax": False,
        }

    def _escape_expert_token(self, value: str) -> str:
        cleaned = re.sub(r"[^\w\s\-]", " ", value, flags=re.UNICODE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return ""
        return '"' + cleaned.replace('"', "") + '"'

    def _normalize_notice(self, notice: dict) -> dict | None:
        external_id = str(notice.get("publication-number") or "").strip()
        if not external_id:
            return None
        title = _localized_text(notice.get("notice-title")) or f"TED notice {external_id}"
        buyer = _localized_text(notice.get("buyer-name"))
        country = self._resolve_country(notice.get("place-of-performance"), notice.get("notice-title"))
        category = self._resolve_category(notice.get("notice-title"), notice.get("contract-nature-main-proc"),
                                          notice.get("main-classification-proc") or notice.get("classification-cpv"))
        source_url = self._html_link(notice.get("links")) or (
            "https://ted.europa.eu/en/notice/-/detail/" + quote(external_id, safe=""))

        estimated_raw = _first_scalar(notice.get("estimated-value-proc"))
        try:
            estimated_value = float(estimated_raw) if estimated_raw else None
        except ValueError:
            estimated_value = None
        currency = _first_scalar(notice.get("estimated-value-cur-proc"))

        return {
            "external_id": external_id, "reference": external_id, "title": title, "buyer": buyer or None,
            "country": country or None, "category": category or None, "source_url": source_url,
            "estimated_value": estimated_value, "currency": currency or None,
            "published_at": _parse_ted_date(_first_scalar(notice.get("publication-date"))),
            "deadline_at": _parse_ted_date(_first_scalar(notice.get("deadline-receipt-tender-date-lot"))),
            "raw": notice,
        }

    def _resolve_country(self, place_of_performance, notice_title) -> str:
        from_place = self.country_resolver.resolve_from_codes(_collect_scalars(place_of_performance))
        if from_place:
            return from_place
        return self._notice_title_segment(notice_title, 0)

    def _resolve_category(self, notice_title, contract_nature, cpv) -> str | None:
        from_title = self._notice_title_segment(notice_title, 1)
        if from_title:
            return from_title
        nature = _first_scalar(contract_nature)
        if nature:
            return nature[:1].upper() + nature[1:].lower()
        cpv_code = _first_scalar(cpv)
        if cpv_code:
            return f"CPV {cpv_code}"
        return None

    def _notice_title_segment(self, notice_title, index: int) -> str:
        text = _localized_text(notice_title)
        if not text:
            return ""
        parts = re.split(r"\s*(?:—|–|-)\s*", text, maxsplit=2)
        return _clean_text(parts[index]) if index < len(parts) else ""

    def _html_link(self, links) -> str:
        if not isinstance(links, dict):
            return ""
        html_links = links.get("html") or links.get("htmlDirect")
        if not isinstance(html_links, dict):
            return ""
        for lang in ("ENG", "eng", "EN", "en"):
            if isinstance(html_links.get(lang), str) and html_links[lang]:
                return html_links[lang]
        for v in html_links.values():
            if isinstance(v, str):
                return v
        return ""


UNGM_BASE_URL = "https://www.ungm.org"
UNGM_SEARCH_URL = "https://www.ungm.org/Public/Notice/Search"

_MONTH_DATE_RE = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{4})(?:\s+(\d{2}:\d{2}))?")


def _parse_ungm_date(value: str, has_time: bool) -> datetime | None:
    value = _clean_text(value)
    if not value:
        return None
    m = _MONTH_DATE_RE.search(value)
    if m:
        date_part, time_part = m.group(1), m.group(2)
        fmt = "%d-%b-%Y %H:%M" if has_time and time_part else "%d-%b-%Y"
        text = f"{date_part} {time_part}" if has_time and time_part else date_part
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        from dateutil import parser as dateutil_parser

        dt = dateutil_parser.parse(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


class UngmNoticeDetailParser:
    """Port of UngmNoticeDetailParser.php (lxml instead of DOMDocument/XPath)."""

    def parse(self, html_content: str) -> dict:
        if not html_content.strip():
            return {}
        try:
            doc = lxml_html.fromstring(html_content)
        except Exception:
            return {}
        roots = doc.xpath('//*[@id="noticeDetail"]')
        if not roots:
            return {}
        root = roots[0]

        metadata = self._parse_metadata(root)
        description = self._text(root, './/div[contains(@class,"ungm-list-item")]/div[contains(@class,"title")]'
                                       '[normalize-space()="Description"]/following-sibling::div[1]')

        result = {
            "agency": self._text(root, './/div[contains(@class,"ungm-panel")]//div[contains(@class,"title")]'
                                       '/span[contains(@class,"highlighted")]') or None,
            "title": self._text(root, './/span[contains(@class,"title") and not(contains(@class,"highlighted"))][1]') or None,
            "notice_type": self._text(root, './/span[contains(@class,"status-tag")]') or None,
            "reference": metadata.get("Reference"),
            "beneficiary_countries": metadata.get("Beneficiary countries or territories"),
            "published_on": metadata.get("Published on"),
            "deadline_on": metadata.get("Deadline on"),
            "description": description or None,
            "contacts": self._parse_contacts(root),
            "links": self._parse_links(root),
            "unspsc": self._parse_unspsc(root),
        }
        return {k: v for k, v in result.items() if v not in (None, [], "")}

    def _parse_metadata(self, root) -> dict:
        metadata: dict[str, str] = {}
        for row in root.xpath('.//div[contains(@class,"row")][.//span[contains(@class,"label")]]'):
            label = self._normalize_label(self._text(row, './/span[contains(@class,"label")]'))
            value = self._text(row, './/span[contains(@class,"value")]')
            if label and value:
                metadata[label] = value
        return metadata

    def _parse_contacts(self, root) -> list[dict]:
        contacts = []
        for block in root.xpath('.//*[@id="contactDetails"]//div[contains(concat(" ", normalize-space(@class), " "), '
                                '" contactDetails ")]'):
            rows = self._parse_label_value_rows(block)
            email = rows.get("Email address")
            first_name = rows.get("First name")
            surname = rows.get("Surname")
            phone = rows.get("Phone") or rows.get("Telephone") or rows.get("Phone number")
            name = " ".join(x for x in (first_name, surname) if x).strip()
            if not name and not email and not phone:
                continue
            contacts.append({"name": name or None, "email": email or None, "phone": phone or None})
        return contacts

    def _parse_links(self, root) -> list[dict]:
        links = []
        for row in root.xpath('.//*[@id="tblLinks"]//tbody/tr'):
            cells = row.xpath("./td")
            url = _clean_text(cells[0].text_content()) if cells else ""
            description = _clean_text(cells[1].text_content()) if len(cells) > 1 else ""
            if not url:
                continue
            links.append({"url": url, "description": description or None})
        return links

    def _parse_unspsc(self, root) -> list[dict]:
        codes = []
        for node in root.xpath('.//*[@id="unspscs-tab"]//div[contains(@class,"unspscNode")][@data-isparent="False"]'):
            parts = node.xpath('.//span[contains(@class,"floatLeft")]')
            if len(parts) < 3:
                continue
            code = _clean_text(parts[0].text_content())
            title = _clean_text(parts[2].text_content())
            if code and title:
                codes.append({"code": code, "title": title})
        return codes

    def _parse_label_value_rows(self, context) -> dict:
        rows: dict[str, str] = {}
        for element in context.xpath('.//div[contains(@class,"row")]'):
            label = self._normalize_label(self._text(element, './/span[contains(@class,"label")]'))
            value_nodes = element.xpath('.//span[contains(@class,"value")]//a | .//span[contains(@class,"value")]')
            value = _clean_text(value_nodes[0].text_content()) if value_nodes else ""
            if label and value:
                rows[label] = value
        return rows

    def _text(self, context, query: str) -> str:
        nodes = context.xpath(query)
        if not nodes:
            return ""
        node = nodes[0]
        text = node.text_content() if hasattr(node, "text_content") else str(node)
        return _clean_text(text)

    def _normalize_label(self, label: str) -> str:
        return label.strip().rstrip(":")


@dataclass
class UngmNoticeConnector:
    detail_parser: UngmNoticeDetailParser = field(default_factory=UngmNoticeDetailParser)
    ingest_filter: IngestFilter = field(default_factory=IngestFilter)
    client: httpx.Client | None = None

    def _http(self) -> httpx.Client:
        return self.client or httpx.Client(timeout=30.0)

    def search(self, filters: dict | None = None) -> dict:
        filters = filters or {}
        payload = {**self._default_payload(), **self._normalize_filters(filters)}
        c = self._http()
        response = c.post(UNGM_SEARCH_URL, json=payload,
                          headers={"Accept": "text/html,application/xhtml+xml",
                                   "User-Agent": "Qiko IDG Sales Intelligence Worker/1.0",
                                   "Referer": UNGM_BASE_URL + "/Public/Notice"})
        if response.status_code >= 400:
            raise RuntimeError(f"UNGM search failed with status {response.status_code}")

        notices = self.parse_notice_rows(response.text)
        enriched = []
        skipped = 0
        for notice in notices:
            detail_notice = self._enrich_with_detail(notice)
            if not self.ingest_filter.passes(detail_notice, filters):
                skipped += 1
                continue
            enriched.append(detail_notice)

        return {"payload": payload, "notices": enriched, "skipped": skipped}

    def fetch_detail(self, notice_id: str) -> dict:
        notice_id = notice_id.strip()
        if not notice_id:
            return {}
        c = self._http()
        response = c.get(f"{UNGM_BASE_URL}/Public/Notice/{quote(notice_id, safe='')}",
                         headers={"Accept": "text/html,application/xhtml+xml",
                                  "User-Agent": "Qiko IDG Sales Intelligence Worker/1.0",
                                  "Referer": UNGM_BASE_URL + "/Public/Notice"})
        if response.status_code >= 400:
            return {}
        return self.detail_parser.parse(response.text)

    def _enrich_with_detail(self, notice: dict) -> dict:
        notice_id = str(notice.get("external_id") or "").strip()
        if not notice_id:
            return notice
        detail = self.fetch_detail(notice_id)
        search_raw = notice.get("raw") if isinstance(notice.get("raw"), dict) else {}
        notice = dict(notice)
        notice["raw"] = {k: v for k, v in {"search": search_raw or None, "detail": detail or None}.items() if v}

        if detail:
            if detail.get("description") and not notice.get("description"):
                notice["description"] = detail["description"]
            if detail.get("beneficiary_countries"):
                notice["country"] = str(detail["beneficiary_countries"]).strip()
            if detail.get("notice_type") and not notice.get("category"):
                notice["category"] = detail["notice_type"]
            if detail.get("reference") and not notice.get("reference"):
                notice["reference"] = detail["reference"]
        return notice

    def parse_notice_rows(self, html_content: str) -> list[dict]:
        if not html_content.strip():
            return []
        try:
            doc = lxml_html.fromstring(html_content)
        except Exception:
            return []

        notices = []
        for row in doc.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " dataRow ")]'):
            notice_id = (row.get("data-noticeid") or "").strip()
            if not notice_id:
                continue
            title = self._text(row, './/*[contains(concat(" ", normalize-space(@class), " "), " resultTitle ")]'
                                    '//*[contains(concat(" ", normalize-space(@class), " "), " ungm-title ")]')
            detail_href = self._attribute(row, './/*[contains(concat(" ", normalize-space(@class), " "), '
                                               '" resultTitle ")]//a[@href]', "href")
            deadline_raw = self._text(row, './/*[contains(concat(" ", normalize-space(@class), " "), " deadline ")]'
                                            "/span[1]")
            published_raw = self._cell_text_by_index(row, 3)
            buyer = self._text(row, './/*[contains(concat(" ", normalize-space(@class), " "), " resultAgency ")]')
            notice_type = self._cell_text_by_index(row, 5)
            reference = self._text(row, './/*[@data-description="Reference"]')
            country = self._cell_text_by_index(row, 7)

            notices.append({
                "external_id": notice_id, "reference": reference,
                "title": title or f"UNGM notice {notice_id}", "buyer": buyer, "country": country,
                "category": notice_type,
                "source_url": self._absolute_url(detail_href or f"/Public/Notice/{notice_id}"),
                "published_at": _parse_ungm_date(published_raw, False),
                "deadline_at": _parse_ungm_date(deadline_raw, True),
                "raw": {"notice_id": notice_id, "reference": reference, "published_raw": published_raw,
                        "deadline_raw": deadline_raw, "notice_type": notice_type},
            })
        return notices

    def _default_payload(self) -> dict:
        return {
            "PageIndex": 0, "PageSize": 15, "Title": "", "Description": "", "Reference": "",
            "PublishedFrom": "", "PublishedTo": "", "DeadlineFrom": "", "DeadlineTo": "",
            "Countries": [], "Agencies": [], "UNSPSCs": [], "NoticeTypes": [],
            "SortField": "DatePublished", "SortAscending": False, "isPicker": False,
            "IsSustainable": False, "IsActive": True, "NoticeDisplayType": None,
            "NoticeSearchTotalLabelId": "noticeSearchTotal", "TypeOfCompetitions": [],
        }

    def _normalize_filters(self, filters: dict) -> dict:
        normalized: dict = {}
        if "query" in filters:
            normalized["Description"] = str(filters["query"])
        if "title" in filters:
            normalized["Title"] = str(filters["title"])
        if "page_size" in filters:
            normalized["PageSize"] = max(1, min(50, int(filters["page_size"])))
        if "page_index" in filters:
            normalized["PageIndex"] = max(0, int(filters["page_index"]))
        if "active_only" in filters:
            normalized["IsActive"] = bool(filters["active_only"])
        return normalized

    def _text(self, row, query: str) -> str:
        nodes = row.xpath(query)
        return _clean_text(nodes[0].text_content()) if nodes else ""

    def _attribute(self, row, query: str, attr: str) -> str:
        nodes = row.xpath(query)
        return (nodes[0].get(attr) or "").strip() if nodes else ""

    def _cell_text_by_index(self, row, index: int) -> str:
        cells = row.xpath('./*[contains(concat(" ", normalize-space(@class), " "), " tableCell ")]')
        if index - 1 < 0 or index - 1 >= len(cells):
            return ""
        return _clean_text(cells[index - 1].text_content())

    def _absolute_url(self, href: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return UNGM_BASE_URL.rstrip("/") + "/" + href.lstrip("/")


# --- Generic HTTP connector (custom sources) -------------------------------------------------
# Best-effort scanner for an arbitrary portal / search URL supplied by the user as a custom source
# (config.url). Detects JSON / RSS-Atom / HTML and extracts a bounded list of notices. Every fetch
# (and every redirect hop) is SSRF-guarded via app.modules.sales_intelligence.ssrf, and automatic
# redirects are disabled so each hop is re-validated. Ported/condensed from the Staging
# GenericHttpNoticeConnector (job-board host presets omitted as out of scope for tender portals).

_GENERIC_MAX_NOTICES = 50
_GENERIC_MAX_BYTES = 5 * 1024 * 1024  # cap response body to 5 MB
_GENERIC_MAX_REDIRECTS = 3
_QUERY_PARAM_KEYS = ("q", "query", "keyword", "keywords", "search", "s")


@dataclass
class GenericHttpNoticeConnector:
    client: httpx.Client | None = None
    ingest_filter: IngestFilter = field(default_factory=IngestFilter)
    resolver: object = None  # injectable getaddrinfo for tests

    def _http(self) -> httpx.Client:
        # follow_redirects stays OFF so every hop is SSRF-revalidated by _fetch.
        return self.client or httpx.Client(timeout=45.0, follow_redirects=False)

    @staticmethod
    def _resolve_query(filters: dict, config: dict) -> str:
        q = str((filters or {}).get("query") or "").strip()
        if q:
            return q
        q = str((config or {}).get("default_query") or "").strip()
        if q:
            return q
        ingest = (config or {}).get("ingest_filters") or {}
        if ingest.get("query_enabled"):
            return str(ingest.get("query_keyword") or "").strip()
        return ""

    @staticmethod
    def _resolve_base_url(config: dict) -> str:
        url = str((config or {}).get("url") or "").strip()
        if url:
            return url
        api_url = str((config or {}).get("api_url") or "").strip()
        # A TED-style POST-only API is not usable by a generic GET.
        if api_url and "api.ted.europa" not in api_url.lower():
            return api_url
        return ""

    @staticmethod
    def _inject_query(base_url: str, query: str) -> str:
        if "{query}" in base_url:
            return base_url.replace("{query}", quote(query, safe=""))
        if not query:
            return base_url
        parts = urlparse(base_url)
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        injected = False
        for key in _QUERY_PARAM_KEYS:
            if key in params:
                params[key] = query
                injected = True
                break
        if not injected and re.search(r"/(search|jobs|find|results)/?", parts.path or "", re.I):
            params["q"] = query
            injected = True
        if not injected:
            return base_url
        return urlunparse(parts._replace(query=urlencode(params)))

    def _build_search_url(self, base_url: str, query: str) -> str:
        return self._inject_query(base_url, query)

    @staticmethod
    def _browser_headers() -> dict:
        return {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,application/json,"
                       "application/rss+xml,*/*;q=0.8"),
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _fetch(self, url: str) -> httpx.Response:
        """SSRF-guarded GET with manual, re-validated redirect handling."""
        client = self._http()
        current = url
        kwargs = {"resolver": self.resolver} if self.resolver is not None else {}
        for _ in range(_GENERIC_MAX_REDIRECTS + 1):
            assert_public_url(current, **kwargs)
            resp = client.get(current, headers=self._browser_headers())
            if resp.is_redirect and resp.headers.get("location"):
                current = urljoin(current, resp.headers["location"])
                continue
            return resp
        raise SsrfError("too many redirects")

    def search(self, filters: dict | None = None, config: dict | None = None) -> dict:
        filters = filters or {}
        config = config or {}
        query = self._resolve_query(filters, config)
        base_url = self._resolve_base_url(config)
        if not base_url:
            raise ValueError("Generic scan requires a valid config.url (search page URL).")
        search_url = self._build_search_url(base_url, query)
        # assert_public_url also runs inside _fetch; call once up front for a clean error message.
        assert_public_url(search_url, **({"resolver": self.resolver} if self.resolver is not None else {}))

        resp = self._fetch(search_url)
        if resp.status_code >= 400:
            hint = {401: " Site blocked automated access.", 403: " Site blocked automated access.",
                    404: " Search URL not found -- check config.url.",
                    405: " Endpoint does not allow GET."}.get(resp.status_code, "")
            raise RuntimeError(f"Generic portal fetch failed with status {resp.status_code} for {search_url}.{hint}")

        body = resp.content[:_GENERIC_MAX_BYTES]
        text = body.decode(resp.encoding or "utf-8", errors="replace")
        content_type = (resp.headers.get("content-type") or "").lower()

        if self._looks_like_json(content_type, text):
            raw = self._parse_json_notices(text, search_url)
            parser = "json"
        elif self._looks_like_feed(content_type, text):
            raw = self._parse_feed_notices(body, search_url)
            parser = "feed"
        else:
            raw = self._parse_html_notices(text, search_url)
            parser = "html"

        # Keyword filter titles unless the keyword was already applied in the URL.
        query_in_url = bool(query) and (quote(query, safe="").lower() in search_url.lower()
                                        or query.lower() in search_url.lower())
        if query and not query_in_url:
            needle = query.lower()
            raw = [n for n in raw
                   if not (f"{n.get('title', '')} {n.get('buyer') or ''} {n.get('category') or ''}".strip())
                   or needle in f"{n.get('title', '')} {n.get('buyer') or ''} {n.get('category') or ''}".lower()]

        raw = raw[:_GENERIC_MAX_NOTICES]
        notices, skipped = [], 0
        for notice in raw:
            if self.ingest_filter.passes(notice, filters):
                notices.append(notice)
            else:
                skipped += 1
        return {"payload": {"url": search_url, "parser": parser, "raw_found": len(raw),
                            "query": query or None}, "notices": notices, "skipped": skipped}

    # -- format detection --
    @staticmethod
    def _looks_like_json(content_type: str, text: str) -> bool:
        if "json" in content_type:
            return True
        stripped = text.lstrip()
        return stripped.startswith("{") or stripped.startswith("[")

    @staticmethod
    def _looks_like_feed(content_type: str, text: str) -> bool:
        if any(t in content_type for t in ("rss", "atom", "xml")):
            return True
        head = text.lstrip()[:512].lower()
        return "<rss" in head or "<feed" in head

    # -- parsers --
    def _parse_json_notices(self, text: str, base_url: str) -> list[dict]:
        try:
            decoded = json.loads(text)
        except ValueError:
            return []
        items = self._find_json_item_list(decoded)
        out = []
        for item in items:
            if isinstance(item, dict):
                n = self._normalize_json_item(item, base_url)
                if n:
                    out.append(n)
        return out

    @staticmethod
    def _find_json_item_list(decoded) -> list:
        if isinstance(decoded, list):
            return decoded
        if isinstance(decoded, dict):
            for key in ("results", "items", "data", "notices", "hits", "records", "jobs"):
                val = decoded.get(key)
                if isinstance(val, list):
                    return val
            for val in decoded.values():  # first list-of-dicts value
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    return val
        return []

    @staticmethod
    def _first(item: dict, keys: tuple) -> str | None:
        for k in keys:
            v = item.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    def _normalize_json_item(self, item: dict, base_url: str) -> dict | None:
        title = self._first(item, ("title", "name", "jobTitle", "headline", "subject"))
        link = self._first(item, ("url", "link", "href", "detailUrl", "detail_url", "permalink"))
        if not title and not link:
            return None
        source_url = urljoin(base_url, link) if link else base_url
        external_id = (self._first(item, ("id", "external_id", "reference", "guid"))
                       or __import__("hashlib").sha1(((link or title) + "|json").encode()).hexdigest())
        return {
            "external_id": str(external_id), "title": title or "Untitled notice", "source_url": source_url,
            "buyer": self._first(item, ("buyer", "company", "organization", "organisation", "agency", "employer")),
            "country": self._first(item, ("country", "countryCode", "location_country")),
            "category": self._first(item, ("category", "type", "sector")),
            "estimated_value": None, "currency": None, "published_at": None, "deadline_at": None,
            "raw": {"format": "json", "item": item},
        }

    def _parse_feed_notices(self, body: bytes, base_url: str) -> list[dict]:
        # Hardened XML parser: no network, no entity resolution (blocks XXE / billion-laughs).
        parser = lxml_etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                                       dtd_validation=False, huge_tree=False)
        try:
            root = lxml_etree.fromstring(body, parser=parser)
        except lxml_etree.XMLSyntaxError:
            return []
        import hashlib

        def _tag(el):
            return lxml_etree.QName(el).localname if el.tag is not lxml_etree.Comment else ""

        out = []
        for el in root.iter():
            name = _tag(el)
            if name not in ("item", "entry"):
                continue
            title, link = "", ""
            for child in el:
                cname = _tag(child)
                if cname == "title" and not title:
                    title = (child.text or "").strip()
                elif cname == "link" and not link:
                    link = (child.get("href") or child.text or "").strip()
            if not title and not link:
                continue
            fmt = "atom" if name == "entry" else "rss"
            out.append({
                "external_id": hashlib.sha1(((link or title) + "|" + fmt).encode()).hexdigest(),
                "title": title or "Untitled notice", "source_url": urljoin(base_url, link) if link else base_url,
                "buyer": None, "country": None, "category": None, "estimated_value": None,
                "currency": None, "published_at": None, "deadline_at": None,
                "raw": {"format": fmt, "title": title, "link": link},
            })
        return out

    def _parse_html_notices(self, text: str, base_url: str) -> list[dict]:
        import hashlib
        try:
            doc = lxml_html.fromstring(text)
        except (ValueError, lxml_etree.ParserError):
            return []
        seen, out = set(), []
        for a in doc.xpath("//a[@href]"):
            title = " ".join(a.text_content().split()).strip()
            href = (a.get("href") or "").strip()
            if len(title) < 12 or not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            source_url = urljoin(base_url, href)
            key = source_url + "|" + title.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "external_id": hashlib.sha1((source_url + "|html").encode()).hexdigest(),
                "title": title, "source_url": source_url, "buyer": None, "country": None,
                "category": None, "estimated_value": None, "currency": None,
                "published_at": None, "deadline_at": None,
                "raw": {"format": "html", "title": title, "href": href},
            })
            if len(out) >= _GENERIC_MAX_NOTICES:
                break
        return out
