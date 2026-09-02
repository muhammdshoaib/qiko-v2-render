"use client";

import { Suspense, useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Badge, Button, SegmentedFilter, type Column } from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import { RowActivityDialog } from "@/components/row-activity-dialog";
import { WorkerSupportDialog } from "@/components/worker-support-dialog";
import { adminMe, listWorkers, type WorkerRow } from "@/lib/api";

const columns: Column<WorkerRow>[] = [
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
];

function WorkersView() {
  const router = useRouter();
  const params = useSearchParams();
  const [active, setActive] = useState<WorkerRow | null>(null);
  const [supportRow, setSupportRow] = useState<WorkerRow | null>(null);
  const availability = params.get("enabled") ?? "";
  const status = params.get("status") ?? "";
  // Same ["admin-me"] query DirectoryPage already runs for this page; TanStack Query dedupes by
  // key, so reading it here to gate "Support view" adds no extra request.
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const canSupportView = me.data?.capabilities?.includes("support_view_worker") ?? false;

  const setFilter = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    next.delete("page");
    router.replace(`?${next.toString()}`, { scroll: false });
  }, [params, router]);

  return (
    <>
    <DirectoryPage<WorkerRow>
      title="Workers"
      noun="workers"
      searchLabel="Search workers by name or id"
      searchPlaceholder="Search by name or id..."
      queryKey="admin-workers"
      filterToken={`${availability}|${status}`}
      onClearFilters={() => router.replace("?", { scroll: false })}
      fetchPage={(search, page, sort) => listWorkers(
        search, page, availability === "" ? undefined : availability === "true", sort,
        status || undefined)}
      rowKey={(row) => `${row.tenant_id}-${row.id}`}
      columns={columns}
      filters={
        <div className="flex flex-wrap items-end gap-4">
          <SegmentedFilter label="Filter by availability" value={availability}
            options={[{ value: "", label: "All" }, { value: "true", label: "Available" },
                      { value: "false", label: "Unavailable" }]}
            onChange={(value) => setFilter("enabled", value)} />
          {/* Status has existed on the server since leg B and had no control. It is the filter that
              answers "which workers are still training", which availability cannot. */}
          <SegmentedFilter label="Filter by status" value={status}
            options={[{ value: "", label: "Any status" }, { value: "training", label: "Training" },
                      { value: "ready", label: "Ready" }]}
            onChange={(value) => setFilter("status", value)} />
        </div>
      }
      actions={(row) => (
        <div className="flex gap-2">
          <Button variant="outline" className="min-h-11" onClick={() => setActive(row)}
            aria-label={`Recent activity for ${row.name}`}>
            Activity
          </Button>
          {row.type === "intelligence" && canSupportView && (
            <Button variant="outline" className="min-h-11" onClick={() => setSupportRow(row)}
              aria-label={`Support view for ${row.name}`}>
              Support view
            </Button>
          )}
        </div>
      )}
      emptyMessage={(filtered) => filtered ? "No workers match this search or filter." : "No workers yet."}
    />
    <RowActivityDialog
      open={Boolean(active)}
      title={active?.name ?? ""}
      subtitle={active ? `${active.tenant_id} / ${active.id}` : undefined}
      targetId={active?.id}
      onClose={() => setActive(null)}
    />
    <WorkerSupportDialog
      open={Boolean(supportRow)}
      agentId={supportRow?.id ?? ""}
      workerName={supportRow?.name ?? ""}
      onClose={() => setSupportRow(null)}
    />
    </>
  );
}

export default function WorkersPage() {
  return <Suspense fallback={null}><WorkersView /></Suspense>;
}
