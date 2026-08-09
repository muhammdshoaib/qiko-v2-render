"use client";

import { Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Alert, Badge, SegmentedFilter, type Column } from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import { adminMe, formatUsd, workerMonitoring, type MonitoredWorker } from "@/lib/api";

const WINDOWS = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
] as const;

function MonitoringView() {
  const router = useRouter();
  const params = useSearchParams();
  const days = Number(params.get("days") ?? 30);
  const availability = params.get("enabled") ?? "";

  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const costVisible = me.data?.capabilities?.includes("view_ai_cost") ?? false;

  const setFilter = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    next.delete("page");
    router.replace(`?${next.toString()}`, { scroll: false });
  }, [params, router]);

  const columns: Column<MonitoredWorker>[] = [
    {
      id: "name", header: "Worker", rowHeader: true, sortable: true,
      cell: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{row.name}</p>
          <p className="truncate text-xs text-muted-foreground">{row.id}</p>
        </div>
      ),
    },
    { id: "tenant", header: "Tenant", sortable: true, hideBelow: "md", cell: (row) => row.tenant_id },
    { id: "calls", header: "Calls", sortable: true, numeric: true,
      cell: (row) => new Intl.NumberFormat().format(row.calls) },
    {
      id: "last_seen", header: "Last used", sortable: true, hideBelow: "md",
      // Derived from real model activity rather than a heartbeat, so an idle worker honestly reads as
      // never used in this window rather than as a stale timestamp.
      cell: (row) => row.last_seen
        ? new Date(row.last_seen).toLocaleDateString()
        : <span className="text-muted-foreground">Not used</span>,
    },
    { id: "status", header: "Status", sortable: true,
      cell: (row) => <Badge variant="muted">{row.status}</Badge> },
    {
      id: "enabled", header: "Availability", sortable: true,
      cell: (row) => (
        <Badge variant={row.enabled ? "default" : "destructive"}>
          {row.enabled ? "Available" : "Unavailable"}
        </Badge>
      ),
    },
    // Present only for a caller holding view_ai_cost. Omitting the column entirely rather than showing
    // an empty one: a blank cell reads as "this worker cost nothing".
    ...(costVisible ? [{
      id: "cost", header: "Spend", numeric: true,
      cell: (row: MonitoredWorker) =>
        row.cost_nano_usd === undefined ? "-" : formatUsd(row.cost_nano_usd),
    } as Column<MonitoredWorker>] : []),
  ];

  return (
    <>
      <DirectoryPage<MonitoredWorker>
        title="Worker Monitoring"
        noun="workers"
        searchLabel="Search workers by name or id"
        searchPlaceholder="Search by name or id..."
        queryKey="worker-monitoring"
        filterToken={`${days}|${availability}`}
        onClearFilters={() => router.replace("?", { scroll: false })}
        // Busiest first is what the endpoint returns unsorted, so the header says so rather than
        // presenting an order the operator cannot account for.
        defaultSort={{ sort: "calls", order: "desc" }}
        // Filtered on the SERVER, not after the fetch. Filtering client-side would leave the total
        // describing the unfiltered set, so the page count and the "showing N of M" line would both
        // be wrong, which is the class of bug this whole leg started from.
        fetchPage={(search, page, sort) => workerMonitoring(
          days, page, undefined, sort, search || undefined,
          availability === "" ? undefined : availability === "true")}
        rowKey={(row) => `${row.tenant_id}-${row.id}`}
        columns={columns}
        filters={
          <div className="flex flex-wrap items-end gap-4">
            <SegmentedFilter label="Time window" value={String(days)}
              options={WINDOWS.map((w) => ({ value: w.value, label: w.label }))}
              onChange={(value) => setFilter("days", value)} />
            <SegmentedFilter label="Filter by availability" value={availability}
              options={[{ value: "", label: "All" }, { value: "true", label: "Available" },
                        { value: "false", label: "Unavailable" }]}
              onChange={(value) => setFilter("enabled", value)} />
          </div>
        }
        emptyMessage={(filtered) => filtered
          ? "No workers match this search or filter."
          : "No worker activity in this window."}
      />
      {me.data && !costVisible && (
        <div className="mx-auto max-w-6xl px-4 pb-6">
          <Alert tone="info">
            Spend is hidden. Showing it needs the View AI cost capability.
          </Alert>
        </div>
      )}
    </>
  );
}

export default function MonitoringPage() {
  return <Suspense fallback={null}><MonitoringView /></Suspense>;
}
