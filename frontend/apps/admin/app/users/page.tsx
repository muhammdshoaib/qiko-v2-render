"use client";

import { Badge } from "@qiko/ui";
import { DirectoryPage } from "@/components/directory-page";
import { listUsers, type UserRow } from "@/lib/api";

export default function UsersPage() {
  return (
    <DirectoryPage<UserRow>
      title="Users"
      searchLabel="Search users by email or name"
      searchPlaceholder="Search by email or name..."
      queryKey="admin-users"
      fetchPage={(search, page) => listUsers(search, page)}
      rowKey={(row) => row.id}
      emptyMessage="No users yet."
      renderRow={(row) => (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-medium">{row.name || row.email}</p>
            <p className="truncate text-xs text-muted-foreground">
              {row.name ? `${row.email} - ` : ""}{row.tenant_id ?? "no tenant"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="muted">{row.role_label}</Badge>
            {/* Platform access is a separate system from the tenant role, so it is labelled as
                such. The scope is only returned to a manage_admins caller, so fall back to the plain
                membership badge rather than rendering nothing. */}
            {row.platform_role
              ? <Badge>Platform {row.platform_role.replace("_", " ")}</Badge>
              : row.is_platform_admin && <Badge>Platform admin</Badge>}
            <span className={row.twofa_enabled ? "text-muted-foreground" : "text-destructive"}>
              {row.twofa_enabled ? "2FA on" : "2FA off"}
            </span>
          </div>
        </div>
      )}
    />
  );
}
