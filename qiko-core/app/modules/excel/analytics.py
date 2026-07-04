"""Workbook analytics + themed report export.

Computes per-numeric-column aggregations (sum/avg/min/max) over a sheet, and exports a report
(XLSX/PDF) via the shared FileGenerator, stored in S3. Exposed as agentcore tools. Ported from the
mcp-parser analyzer/exporter, simplified to the aggregations that back the dashboard.
"""
from __future__ import annotations

from app.modules.chat.files import FileGenerator


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def compute_analytics(rows: list[list]) -> dict:
    """rows[0] = header. Returns per-numeric-column stats + row count."""
    if not rows:
        return {"row_count": 0, "columns": {}}
    header = [str(c) if c is not None else f"col{i}" for i, c in enumerate(rows[0])]
    data = rows[1:]
    columns: dict[str, dict] = {}
    for i, name in enumerate(header):
        nums = [r[i] for r in data if i < len(r) and _is_number(r[i])]
        if nums:
            columns[name] = {"sum": sum(nums), "avg": round(sum(nums) / len(nums), 2),
                             "min": min(nums), "max": max(nums), "count": len(nums)}
    return {"row_count": len(data), "columns": columns}


def export_report(generator: FileGenerator, tenant: str, source: str, analytics: dict,
                  *, fmt: str = "xlsx") -> str:
    """Render the analytics as a report artifact and store it; returns the download key."""
    header = ["metric", "column", "value"]
    rows = [header]
    for col, stats in analytics.get("columns", {}).items():
        for metric, value in stats.items():
            rows.append([metric, col, value])
    if fmt == "xlsx":
        return generator.generate(tenant, "xlsx", f"{source}-report", {"sheet": "Analytics", "rows": rows})
    paragraphs = [f"Rows analysed: {analytics.get('row_count', 0)}"] + \
        [f"{col} {m}={v}" for col, s in analytics.get("columns", {}).items() for m, v in s.items()]
    return generator.generate(tenant, "pdf", f"{source}-report", {"title": f"{source} report", "paragraphs": paragraphs})
