"""GA4 (Google Analytics Data API) dashboard analytics.

The Google client sits behind a GA4Gateway protocol so the report-shaping + resilience logic is
testable without the network. Shapes overview KPIs and top dimensions from a report, with a
resilient shift-back: if the window has no data (common for very recent ranges) it retries an
earlier window before giving up.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class GA4Gateway(Protocol):
    def run_report(self, start: str, end: str, metrics: list[str], dimensions: list[str]) -> list[dict]: ...


def _sum(rows: list[dict], metric: str) -> float:
    return sum(float(r.get(metric, 0) or 0) for r in rows)


def top_by(rows: list[dict], dimension: str, metric: str, *, n: int = 5) -> list[dict]:
    ranked = sorted(rows, key=lambda r: float(r.get(metric, 0) or 0), reverse=True)
    return [{dimension: r.get(dimension), metric: float(r.get(metric, 0) or 0)} for r in ranked[:n]]


@dataclass
class GA4Analytics:
    gateway: GA4Gateway
    strict: bool = False

    def _report(self, start: str, end: str, dims: list[str]) -> list[dict]:
        return self.gateway.run_report(start, end, ["sessions", "activeUsers"], dims)

    def dashboard(self, start: str, end: str, *, fallback_start: str | None = None) -> dict:
        rows = self._report(start, end, ["pagePath"])
        if not rows and fallback_start and not self.strict:
            rows = self._report(fallback_start, end, ["pagePath"])  # resilient shift-back
        return {
            "sessions": _sum(rows, "sessions"),
            "active_users": _sum(rows, "activeUsers"),
            "top_pages": top_by(rows, "pagePath", "sessions"),
            "had_data": bool(rows),
        }
