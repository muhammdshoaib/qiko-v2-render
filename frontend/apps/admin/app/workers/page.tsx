"use client";

import { useState } from "react";
import { Badge, Button } from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import { listWorkers, type WorkerRow } from "@/lib/api";

type Filter = "all" | "enabled" | "disabled";

export default function WorkersPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const enabled = filter === "all" ? undefined : filter === "enabled";

  return (
    <DirectoryPage<WorkerRow>
      title="Workers"
      searchLabel="Search workers by name or id"
      searchPlaceholder="Search by name or id..."
      queryKey="admin-workers"
      filterToken={filter}
      fetchPage={(search, page) => listWorkers(search, page, enabled)}
      rowKey={(row) => `${row.tenant_id}-${row.id}`}
      emptyMessage="No workers match this filter."
      filters={
        <div role="group" aria-label="Filter by state" className="flex gap-2">
          {(["all", "enabled", "disabled"] as Filter[]).map((option) => (
            <Button key={option} className="min-h-11"
              variant={filter === option ? "default" : "outline"}
              aria-pressed={filter === option}
              onClick={() => setFilter(option)}>
              {option === "all" ? "All" : option === "enabled" ? "Enabled" : "Disabled"}
            </Button>
          ))}
        </div>
      }
      renderRow={(row) => (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-medium">{row.name}</p>
            <p className="truncate text-xs text-muted-foreground">{row.tenant_id} - {row.id}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="muted">{row.status}</Badge>
            <Badge variant={row.enabled ? "default" : "destructive"}>
              {row.enabled ? "Enabled" : "Disabled"}
            </Badge>
          </div>
        </div>
      )}
    />
  );
}
