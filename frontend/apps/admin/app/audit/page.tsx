"use client";

/**
 * The audit log viewer.
 *
 * Five waves of instrumentation and a retention policy produced a table nobody could open. This is the
 * surface that makes any of it useful, and it is shaped by two things the research was clear about.
 *
 * All filter state lives in the URL, so a link is shareable in a ticket. That is the single most used
 * feature of an audit viewer in practice: an operator does not search, they are sent a link.
 *
 * There is no total and no page numbers. A COUNT over a filtered multi-million-row table is what makes
 * these pages unusable, and the number is not worth a full scan. "Load more" plus a cursor is what
 * GitHub does for the same reason.
 */
import { Suspense, useCallback, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Alert, Badge, Button, Card, CardContent, Checkbox, DataTable, Input, SegmentedFilter, Select,
  Skeleton, type Column,
} from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { AuditDetail } from "@/components/audit-detail";
import { auditCatalogue, auditEvents, auditRetention, type AuditEvent } from "@/lib/api";
import {
  ACTOR_LABELS, AUTOMATED_ACTORS, CATEGORY_LABELS, OUTCOME_TONE, formatWhen, headline,
  relativeWhen,
} from "@/lib/audit-format";

const WINDOWS = [
  { value: "1", label: "24 hours" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
] as const;

const PAGE = 50;

function AuditView() {
  const router = useRouter();
  const params = useSearchParams();
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);

  // Reading straight from the URL rather than mirroring it into state: two sources of truth for a
  // filter is how a shareable link ends up not reproducing what the sender was looking at.
  const filters = useMemo(() => ({
    days: Number(params.get("days") ?? 7),
    category: params.get("category") ?? "",
    action: params.get("action") ?? "",
    outcome: params.get("outcome") ?? "",
    tenant_id: params.get("tenant") ?? "",
    actor_id: params.get("actor") ?? "",
    target_id: params.get("target") ?? "",
    request_id: params.get("request") ?? "",
    search: params.get("q") ?? "",
  }), [params]);
  const hideAutomated = params.get("humans") === "1";

  const setFilter = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    setCursors([null]);  // a changed filter invalidates every cursor built against the old one
    setSelected(null);
    router.replace(`/audit?${next.toString()}`);
  }, [params, router]);

  const cursor = cursors[cursors.length - 1];
  const events = useQuery({
    queryKey: ["audit", filters, cursor],
    queryFn: () => auditEvents({ ...filters, cursor, limit: PAGE }),
    // Keeps the rows on screen while the next page loads instead of collapsing into skeletons.
    placeholderData: keepPreviousData,
  });
  const catalogue = useQuery({ queryKey: ["audit-catalogue"], queryFn: auditCatalogue });
  const retention = useQuery({ queryKey: ["audit-retention"], queryFn: auditRetention });

  const rows = useMemo(() => {
    const items = events.data?.items ?? [];
    // Client-side, and only this one: "hide automated actors" is the highest-value control in the whole
    // view (it turns a noisy stream into a stream of human decisions) and it is a property of a row we
    // already have, so a round trip would be worse than free.
    return hideAutomated ? items.filter((e) => !AUTOMATED_ACTORS.includes(e.actor_type)) : items;
  }, [events.data, hideAutomated]);

  const visibleActions = useMemo(() => {
    const all = catalogue.data?.actions ?? [];
    return filters.category ? all.filter((a) => a.category === filters.category) : all;
  }, [catalogue.data, filters.category]);

  const columns: Column<AuditEvent>[] = [
    {
      id: "occurred_at", header: "When", sortable: false,
      cell: (row) => (
        <span title={row.occurred_at} className="whitespace-nowrap">
          <span className="block">{relativeWhen(row.occurred_at)}</span>
          <span className="block text-xs text-muted-foreground">{formatWhen(row.occurred_at)}</span>
        </span>
      ),
    },
    {
      id: "message", header: "Event", rowHeader: true,
      // The sentence, not the action code. The code is in the drawer for anyone who wants it.
      cell: (row) => (
        <button type="button" onClick={() => setSelected(row)}
          className="text-left underline decoration-dotted underline-offset-2 hover:decoration-solid focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {headline(row)}
        </button>
      ),
    },
    {
      id: "actor_type", header: "Actor", hideBelow: "lg",
      cell: (row) => (
        <span className="text-xs">
          <Badge variant="muted">{ACTOR_LABELS[row.actor_type] ?? row.actor_type}</Badge>
        </span>
      ),
    },
    {
      id: "tenant_id", header: "Tenant", hideBelow: "lg",
      cell: (row) => row.tenant_id
        ? <button type="button" className="underline decoration-dotted"
            onClick={() => setFilter("tenant", row.tenant_id!)}>{row.tenant_id}</button>
        // Not a dash: platform-scope is a real value, and showing it as missing would be wrong.
        : <span className="text-muted-foreground">Platform</span>,
    },
    {
      id: "outcome", header: "Outcome",
      cell: (row) => row.outcome === "success"
        ? <span className="text-xs text-muted-foreground">Success</span>
        : <Badge variant={OUTCOME_TONE[row.outcome] === "error" ? "destructive" : "warning"}>
            {row.outcome === "denied" ? "Denied" : "Failed"}
          </Badge>,
    },
  ];

  return (
    <AppShell title="Audit Log">
      <div className="mx-auto max-w-7xl space-y-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>
            Audit Log
          </h1>
          <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
            {events.isLoading ? "Loading events..."
              : events.isError ? "Could not load the audit log."
                : `${rows.length} event${rows.length === 1 ? "" : "s"} in the last ${filters.days} day${filters.days === 1 ? "" : "s"}${events.data?.has_more ? ", more available" : ""}`}
          </p>
        </div>

        {/* Told plainly rather than left as a silent gap. An operator without the spend capability
            would otherwise conclude that no cost caps had ever been changed. */}
        {(events.data?.hidden_actions ?? 0) > 0 && (
          <Alert tone="info">
            {events.data!.hidden_actions} action type{events.data!.hidden_actions === 1 ? " is" : "s are"} hidden
            from you. Spend and platform-authority events need their own capability.
          </Alert>
        )}

        <div className="grid gap-5 lg:grid-cols-[16rem_1fr]">
          <Card>
            <CardContent className="space-y-4 pt-6">
              <SegmentedFilter
                label="Time range"
                value={String(filters.days)}
                options={WINDOWS.map((w) => ({ value: w.value, label: w.label }))}
                onChange={(value) => setFilter("days", value)}
              />

              <label className="block space-y-1 text-sm">
                <span className="font-medium">Category</span>
                <Select value={filters.category}
                  onChange={(e) => { setFilter("category", e.target.value); setFilter("action", ""); }}>
                  <option value="">All categories</option>
                  {(catalogue.data?.categories ?? []).map((c) => (
                    <option key={c} value={c}>{CATEGORY_LABELS[c] ?? c}</option>
                  ))}
                </Select>
              </label>

              <label className="block space-y-1 text-sm">
                <span className="font-medium">Action</span>
                <Select value={filters.action} onChange={(e) => setFilter("action", e.target.value)}>
                  <option value="">All actions</option>
                  {visibleActions.map((a) => (
                    <option key={a.action} value={a.action}>{a.action.split(".")[1] ?? a.action}</option>
                  ))}
                </Select>
              </label>

              <label className="block space-y-1 text-sm">
                <span className="font-medium">Outcome</span>
                <Select value={filters.outcome} onChange={(e) => setFilter("outcome", e.target.value)}>
                  <option value="">Any outcome</option>
                  <option value="failure">Failures only</option>
                  <option value="denied">Denials only</option>
                  <option value="success">Successes only</option>
                </Select>
              </label>

              <label className="flex items-start gap-2 text-sm">
                <Checkbox checked={hideAutomated}
                  onChange={(e) => setFilter("humans", e.target.checked ? "1" : "")} />
                <span>
                  <span className="font-medium">People only</span>
                  <span className="block text-xs text-muted-foreground">
                    Hides scheduled jobs and webhooks.
                  </span>
                </span>
              </label>

              <label className="block space-y-1 text-sm">
                <span className="font-medium">Search</span>
                <Input value={filters.search} placeholder="Event, actor or target"
                  onChange={(e) => setFilter("q", e.target.value)} />
              </label>

              {(filters.tenant_id || filters.actor_id || filters.target_id || filters.request_id) && (
                <Button variant="outline" className="w-full"
                  onClick={() => router.replace(`/audit?days=${filters.days}`)}>
                  Clear narrowed view
                </Button>
              )}

              {/* Stated on the page, not only in a policy document. It prevents the "the log is
                  missing data" ticket and shows an auditor the policy is visible to its users. */}
              {retention.data && (
                <p className="border-t border-border pt-3 text-xs text-muted-foreground">
                  Events are kept for {Math.round(retention.data.event_retention_days / 30)} months.
                  Network addresses are removed after {Math.round(retention.data.network_retention_days / 30)} months.
                </p>
              )}
            </CardContent>
          </Card>

          <div className="space-y-4">
            {events.isError && <Alert tone="error">The audit log could not be loaded.</Alert>}
            {events.isLoading
              ? <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12" />)}</div>
              : (
                <>
                  <DataTable
                    caption="Platform audit events, newest first"
                    columns={columns}
                    rows={rows}
                    rowKey={(row) => row.event_id}
                    stale={events.isPlaceholderData}
                    empty={
                      <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
                        {filters.category || filters.action || filters.search || filters.outcome
                          ? "No events match these filters."
                          : hideAutomated
                            ? "No events from people in this window. Automated actors are hidden."
                            : "No events recorded in this window."}
                      </CardContent></Card>
                    }
                  />

                  <div className="flex items-center justify-between gap-3">
                    <Button variant="outline" disabled={cursors.length === 1}
                      onClick={() => { setCursors((c) => c.slice(0, -1)); setSelected(null); }}>
                      Previous
                    </Button>
                    {/* No page number, because there is no total to number against. */}
                    <span className="text-sm text-muted-foreground">
                      {cursors.length > 1 ? `Page ${cursors.length}` : ""}
                    </span>
                    <Button variant="outline"
                      disabled={!events.data?.has_more || !events.data?.next_cursor}
                      onClick={() => {
                        const next = events.data?.next_cursor;
                        if (next) { setCursors((c) => [...c, next]); setSelected(null); }
                      }}>
                      Load older
                    </Button>
                  </div>
                </>
              )}
          </div>
        </div>

        <AuditDetail
          event={selected}
          onClose={() => setSelected(null)}
          onFilter={setFilter}
        />
      </div>
    </AppShell>
  );
}

export default function AuditPage() {
  // useSearchParams needs a Suspense boundary in the app router.
  return <Suspense fallback={null}><AuditView /></Suspense>;
}
