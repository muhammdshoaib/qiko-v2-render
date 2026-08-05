"use client";

import { Badge } from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import { listTenants, type TenantRow } from "@/lib/api";

export default function TenantsPage() {
  return (
    <DirectoryPage<TenantRow>
      title="Tenants"
      searchLabel="Search tenants by email or id"
      searchPlaceholder="Search by email..."
      queryKey="admin-tenants"
      fetchPage={(search, page) => listTenants(search, page)}
      rowKey={(row) => row.tenant_id}
      emptyMessage="No tenants yet."
      renderRow={(row) => (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-medium">{row.email}</p>
            <p className="truncate text-xs text-muted-foreground">{row.tenant_id}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="muted">{row.plan}</Badge>
            {row.is_studio && <Badge>Studio</Badge>}
            <span className="text-muted-foreground">
              {row.user_count} {row.user_count === 1 ? "user" : "users"}
            </span>
            <span className="text-muted-foreground">
              {row.worker_count} {row.worker_count === 1 ? "worker" : "workers"}
            </span>
            <span className="tabular-nums">
              {(row.earnings_cents / 100).toLocaleString(undefined, { style: "currency", currency: "GBP" })}
            </span>
          </div>
        </div>
      )}
    />
  );
}
