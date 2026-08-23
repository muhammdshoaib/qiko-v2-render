"use client";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, CardContent, Input } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  ALL_CAPABILITIES,
  adminMe,
  grantPlatformAdmin,
  listPlatformAdmins,
  listPlatformAdminAudit,
  removePlatformAdmin,
  type AdminRole,
  type Capability,
} from "@/lib/api";

const LABELS: Record<Capability, string> = {
  view_audit: "Read the audit log",
  view_customers: "View customers",
  manage_customers: "Manage customers",
  manage_workers: "Manage workers",
  manage_billing: "Manage billing",
  manage_admins: "Manage admins",
  view_ai_cost: "View AI cost",
  view_system_stats: "View system stats",
  set_cost_caps: "Set cost caps",
};

/** Removing an admin used to go through window.confirm: unstyleable, unannounced to assistive tech,
 *  and it gave no place to record the reason that the audit trail stores. This is the same native
 *  <dialog> pattern the customer detail view already uses, including focus restore to the trigger. */
function ConfirmRemoval({ email, reason, onReasonChange, opener, onConfirm, onCancel, pending }: {
  email: string | null;
  reason: string;
  onReasonChange: (value: string) => void;
  opener: HTMLElement | null;
  onConfirm: () => void;
  onCancel: () => void;
  pending: boolean;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (email && !dialog.open) dialog.showModal();
    if (!email && dialog.open) dialog.close();
  }, [email]);

  const close = () => {
    onCancel();
    // The element must be back in the layout before it can take focus.
    requestAnimationFrame(() => opener?.focus());
  };

  return (
    <dialog ref={dialogRef} aria-labelledby="confirm-removal-title"
      onClose={close}
      // Escape must not abandon a request that is already in flight.
      onCancel={(event) => { if (pending) event.preventDefault(); }}
      className="m-auto max-h-[90dvh] w-[min(92vw,28rem)] overflow-y-auto rounded-2xl border border-border bg-card p-5 text-foreground backdrop:bg-black/50">
      <h2 id="confirm-removal-title" className="text-lg font-semibold">Remove platform access</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {email} will lose access to the admin console. This is recorded in the audit trail.
      </p>
      <label className="mt-4 block">
        <span className="text-sm">Reason (optional)</span>
        <Input className="mt-1" value={reason} onChange={(event) => onReasonChange(event.target.value)}
          placeholder="Why is access being removed?" />
      </label>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="outline" className="min-h-11" disabled={pending} onClick={close}>Cancel</Button>
        <Button variant="destructive" className="min-h-11" disabled={pending} onClick={onConfirm}>
          {pending ? "Removing..." : "Remove access"}
        </Button>
      </div>
    </dialog>
  );
}

export default function AdminsPage() {
  const [pendingRemoval, setPendingRemoval] = useState<string | null>(null);
  const removeOpener = useRef<HTMLElement | null>(null);
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const admins = useQuery({ queryKey: ["platform-admins"], queryFn: listPlatformAdmins });
  const audit = useQuery({ queryKey: ["platform-admin-audit"], queryFn: () => listPlatformAdminAudit() });

  const canManage = me.data?.capabilities?.includes("manage_admins") ?? false;
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<AdminRole>("viewer");
  const [selected, setSelected] = useState<Capability[]>([]);
  const [useDefaults, setUseDefaults] = useState(true);
  const [reason, setReason] = useState("");

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["platform-admins"] });
    void qc.invalidateQueries({ queryKey: ["platform-admin-audit"] });
  };
  const grant = useMutation({
    mutationFn: () => grantPlatformAdmin(email.trim(), {
      role,
      capabilities: useDefaults ? null : selected,
      reason: reason.trim() || undefined,
    }),
    onSuccess: () => { setEmail(""); setReason(""); refresh(); },
  });
  const remove = useMutation({
    mutationFn: (target: string) => removePlatformAdmin(target, reason.trim() || undefined),
    onSuccess: () => { setReason(""); refresh(); },
  });

  return (
    <AppShell title="Platform Admins">
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Platform Admins</h1>
          <p className="text-sm text-muted-foreground">
            Everyone with platform-wide access, and exactly what each of them can do.
          </p>
        </div>

        {admins.isError && (
          <p role="alert" className="text-sm text-destructive">
            Could not load the admin directory.{" "}
            <button className="underline" onClick={() => admins.refetch()}>Retry</button>
          </p>
        )}

        <Card>
          <CardContent className="space-y-3 py-4">
            {admins.isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
            {admins.data?.admins.length === 0 && (
              <p className="text-sm text-muted-foreground">No platform admins yet.</p>
            )}
            {admins.data?.admins.map((admin) => (
              <div key={admin.email} className="flex flex-wrap items-center justify-between gap-2 border-b pb-3 last:border-0 last:pb-0">
                <div>
                  <p className="font-medium">{admin.email}</p>
                  <p className="text-xs text-muted-foreground">
                    {admin.role} - {admin.capabilities.map((c) => LABELS[c] ?? c).join(", ")}
                  </p>
                </div>
                {/* A super_admin cannot be removed through the API (409): the recovery path is the
                    operator CLI, so offering the button would only produce an error. */}
                {canManage && admin.role !== "super_admin" && (
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={remove.isPending}
                    onClick={(event) => {
                      removeOpener.current = event.currentTarget;
                      setPendingRemoval(admin.email);
                    }}
                    aria-label={`Remove ${admin.email} from platform administration`}
                  >
                    Remove
                  </Button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        {!canManage && (
          <p role="status" className="text-sm text-muted-foreground">
            Read-only access: managing platform admins needs the Manage admins capability.
          </p>
        )}

        {canManage && (
          <Card>
            <CardContent className="space-y-3 py-4">
              <p className="font-medium">Grant or update access</p>
              <Input type="email" aria-label="Admin email" placeholder="colleague@company.com"
                value={email} onChange={(event) => setEmail(event.target.value)} />
              <label className="block text-sm">
                Role
                <select aria-label="Role" className="ml-2 rounded border bg-background p-1"
                  value={role} onChange={(event) => setRole(event.target.value as AdminRole)}>
                  <option value="viewer">viewer</option>
                  <option value="super_admin">super_admin</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={useDefaults}
                  onChange={(event) => setUseDefaults(event.target.checked)} />
                Use the role&apos;s default capabilities
              </label>
              {!useDefaults && (
                <fieldset className="grid grid-cols-2 gap-1 text-sm">
                  <legend className="sr-only">Capabilities</legend>
                  {ALL_CAPABILITIES.map((capability) => (
                    <label key={capability} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selected.includes(capability)}
                        onChange={(event) =>
                          setSelected((current) => event.target.checked
                            ? [...current, capability]
                            : current.filter((item) => item !== capability))}
                      />
                      {LABELS[capability]}
                    </label>
                  ))}
                </fieldset>
              )}
              <Input aria-label="Reason" placeholder="Reason (recorded in the audit trail)"
                value={reason} onChange={(event) => setReason(event.target.value)} />
              <Button disabled={!email.includes("@") || grant.isPending} onClick={() => grant.mutate()}>
                {grant.isPending ? "Saving..." : "Save access"}
              </Button>
              {grant.isError && (
                <p role="alert" className="text-sm text-destructive">Could not save that grant.</p>
              )}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardContent className="space-y-2 py-4">
            <p className="font-medium">Access history</p>
            {audit.data?.entries.length === 0 && (
              <p className="text-sm text-muted-foreground">No changes recorded yet.</p>
            )}
            {audit.data?.entries.map((entry) => (
              <p key={`${entry.id}-${entry.created_at}`} className="text-xs text-muted-foreground">
                {new Date(entry.created_at).toLocaleString()} - {entry.changed_by_email} set{" "}
                {entry.email} to {entry.role ?? "no access"}
                {entry.previous_role ? ` (was ${entry.previous_role})` : ""}
                {entry.reason ? ` - ${entry.reason}` : ""}
              </p>
            ))}
          </CardContent>
        </Card>
      </div>
      <ConfirmRemoval
        email={pendingRemoval}
        reason={reason}
        onReasonChange={setReason}
        opener={removeOpener.current}
        pending={remove.isPending}
        onCancel={() => setPendingRemoval(null)}
        onConfirm={() => {
          if (pendingRemoval) remove.mutate(pendingRemoval);
          setPendingRemoval(null);
        }}
      />
    </AppShell>
  );
}
