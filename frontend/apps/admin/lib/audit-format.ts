/**
 * Turning audit rows into something a person can read.
 *
 * The dominant failure of a homegrown audit viewer is rendering two raw JSON blobs side by side and
 * calling it a diff. Everything here exists to avoid that: a field knows how to format itself, money
 * is money rather than an integer count of nano-dollars, a boolean reads as the state it describes,
 * and a changed secret says it changed without pretending there is a value to reveal.
 */
import type { AuditEvent } from "./api";

/** Actions grouped for the filter rail. The backend supplies the taxonomy; these are just the labels. */
export const CATEGORY_LABELS: Record<string, string> = {
  auth: "Authentication",
  access: "Access and membership",
  admin: "Tenants and workers",
  billing: "Money",
  config: "Configuration and credentials",
  data: "Customer data",
  privacy: "Privacy operations",
};

/** Actor kinds. The distinction that matters most in practice is people versus everything else: an
 *  operator scanning for a human decision wants the scheduler and the webhooks out of the way. */
export const ACTOR_LABELS: Record<string, string> = {
  user: "Tenant user",
  platform_admin: "Platform admin",
  system: "System",
  job: "Scheduled job",
  webhook: "Webhook",
  anonymous: "Unauthenticated",
};

export const AUTOMATED_ACTORS = ["system", "job", "webhook"];

/** Fields whose value is a money amount in the given unit, so 5000000000 reads as $5.00 rather than as
 *  a number nobody can parse at a glance. */
const NANO_USD_FIELDS = new Set(["monthly_cap_nano_usd", "cost_nano_usd"]);
const CENTS_FIELDS = new Set(["amount_cents", "earnings_cents"]);

/** Fields that describe a credential. Rendered as a state, never as a value or a masked placeholder:
 *  a placeholder invites a reader to think there is something to reveal. */
const SECRET_FIELDS = new Set(["key", "key_name", "fingerprint_before", "fingerprint_after"]);

const FIELD_LABELS: Record<string, string> = {
  is_studio: "Studio access",
  monthly_cap_nano_usd: "Monthly spend cap",
  alert_threshold_pct: "Alert threshold",
  amount_cents: "Amount",
  passages_removed: "Passages removed",
  messages_removed: "Messages removed",
  file_count: "Files deleted",
  rows_pseudonymised: "Rows pseudonymised",
  request_ref: "Request reference",
  links_marked: "Links marked",
  events_deleted: "Events deleted",
  addresses_cleared: "Addresses cleared",
  customer_email: "Customer",
  key: "Credential field",
  provider: "Provider",
  result: "Result",
  status: "Status",
  role: "Role",
  state: "State",
  method: "Method",
  enabled: "Available",
  plan: "Plan",
  doc_id: "Document",
  sections: "Sections",
  questions: "Questions",
  recurring: "Recurring",
};

export const fieldLabel = (field: string): string =>
  FIELD_LABELS[field] ?? field.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

const money = (amount: number, divisor: number): string =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount / divisor);

/**
 * Format one side of a diff.
 *
 * Returns a string rather than a node so the same function serves the table, the CSV export and any
 * future surface. `null` and `undefined` become an explicit dash rather than an empty cell, because an
 * empty cell reads as "we did not record this" when the truth is "there was no value".
 */
export function formatValue(field: string, value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (SECRET_FIELDS.has(field)) {
    // The audit deliberately holds no credential values. Showing the field NAME is the whole content.
    return typeof value === "string" ? value : "changed";
  }
  if (typeof value === "boolean") {
    // Read as the state, not as true/false. "Studio access: Off -> On" is a sentence; "false -> true"
    // makes the reader map it back to the field themselves.
    if (field === "enabled") return value ? "Available" : "Unavailable";
    if (field === "is_studio") return value ? "On" : "Off";
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    if (NANO_USD_FIELDS.has(field)) return value === 0 ? "No cap" : `${money(value, 1e9)}/mo`;
    if (CENTS_FIELDS.has(field)) return money(value, 100);
    if (field === "alert_threshold_pct") return `${value}%`;
    return new Intl.NumberFormat("en-US").format(value);
  }
  if (Array.isArray(value)) return value.length ? value.join(", ") : "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export type ChangeRow = { field: string; label: string; from: string; to: string };

/** The diff as rows. Unchanged fields are absent by construction on the server, so there is no
 *  "show unchanged" toggle to build and nothing to filter here. */
export function changeRows(event: AuditEvent): ChangeRow[] {
  return Object.entries(event.changes ?? {}).map(([field, delta]) => ({
    field,
    label: fieldLabel(field),
    from: formatValue(field, delta?.from),
    to: formatValue(field, delta?.to),
  }));
}

/** Absolute, with the timezone named. Every auditor conversation happens in UTC and every operator
 *  thinks in local time, so the row shows local and the drawer shows both. */
export function formatWhen(iso: string): string {
  const at = new Date(iso);
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(at);
}

export function formatWhenUtc(iso: string): string {
  const at = new Date(iso);
  return `${new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    timeZone: "UTC",
  }).format(at)} UTC`;
}

export function relativeWhen(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] =
    [["day", 86400], ["hour", 3600], ["minute", 60]];
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return formatter.format(-Math.round(seconds / size), unit);
  }
  return formatter.format(-seconds, "second");
}

/** Outcome tone. `denied` is separated from `failure` on purpose: one is somebody being refused, the
 *  other is something breaking, and during an incident they lead in different directions. */
export const OUTCOME_TONE: Record<string, "neutral" | "warning" | "error"> = {
  success: "neutral",
  failure: "error",
  denied: "warning",
};

/** The sentence the server rendered at write time, falling back to the action if there is none. Never
 *  re-rendered here: a sentence rebuilt from current labels would change retroactively when something
 *  is renamed, which is the opposite of what an audit record is for. */
export const headline = (event: AuditEvent): string => event.message || event.action;
