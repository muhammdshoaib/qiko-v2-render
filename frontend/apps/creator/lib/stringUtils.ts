// Locale-safe short date (e.g. "14 Mar 2025"). Accepts ISO date strings / anything Date can parse;
// returns an em dash for empty/invalid input so callers never render a raw "2025-03-14" string.
export function formatShortDate(value?: string | null): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

// Locale-safe date + time (e.g. "14 Mar 2025, 4:30 pm"). Same em-dash fallback as formatShortDate.
export function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) +
    `, ${d.toLocaleTimeString("en-GB", { hour: "numeric", minute: "2-digit" })}`;
}

export function toTitleFromSlug(value?: string | null): string {
  if (!value) return "";
  const cleaned = value.replace(/_/g, " ").trim();
  if (!cleaned) return "";
  return cleaned
    .toLowerCase()
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

// Human-readable label for a worker's vertical / type (`Agent.atype`). Centralised here so the
// dashboard, workers list and worker detail all display the SAME humanised vertical instead of
// generic "General" / "Worker" / "General purpose" copy. Unknown/legacy values fall back to a
// title-cased slug, and a blank value reads as a plain "AI Worker".
export function workerTypeLabel(atype?: string | null): string {
  switch ((atype ?? "").trim()) {
    case "worker":
      return "AI Worker";
    case "pre_sales_writer":
      return "Pre-Sales Writer";
    case "sales_intelligence":
      return "Sales Intelligence";
    case "finance":
      return "Financial Analyst";
    case "intelligence":
      return "Investor Concierge";
    default:
      return atype ? toTitleFromSlug(atype) : "AI Worker";
  }
}

