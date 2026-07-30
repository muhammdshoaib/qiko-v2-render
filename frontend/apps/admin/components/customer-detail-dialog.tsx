"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { Badge, Button, Card, CardContent, Input } from "@qiko/ui";
import {
  customerDetail,
  setCustomerStudio,
  setWorkerEnabled,
  type AdminRole,
  type AdminWorker,
} from "@/lib/api";

export function CustomerDetailDialog({ customerId, role, opener, onClose }: {
  customerId: string | null;
  role: AdminRole;
  opener: HTMLElement | null;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const confirmDialogRef = useRef<HTMLDialogElement>(null);
  const confirmTrigger = useRef<HTMLElement | null>(null);
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["admin-customer", customerId],
    queryFn: () => customerDetail(customerId!),
    enabled: !!customerId,
  });
  const [confirmWorker, setConfirmWorker] = useState<AdminWorker | null>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (customerId && dialog && !dialog.open) dialog.showModal();
  }, [customerId]);

  useEffect(() => {
    const dialog = confirmDialogRef.current;
    if (confirmWorker && dialog && !dialog.open) dialog.showModal();
  }, [confirmWorker]);

  function close() {
    dialogRef.current?.close();
  }

  function closeConfirmation() {
    confirmDialogRef.current?.close();
  }

  function restoreConfirmationFocus() {
    setConfirmWorker(null);
    setReason("");
    requestAnimationFrame(() => confirmTrigger.current?.focus());
  }

  function restoreAndClose() {
    setConfirmWorker(null);
    setReason("");
    onClose();
    requestAnimationFrame(() => opener?.focus());
  }

  const studioUpdate = useMutation({
    mutationFn: () => setCustomerStudio(customerId!, !detail.data!.is_studio),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-customer", customerId] }),
  });

  const update = useMutation({
    mutationFn: () => setWorkerEnabled(customerId!, confirmWorker!.id, !confirmWorker!.enabled, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-customer", customerId] });
      closeConfirmation();
    },
  });

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="customer-detail-title"
      onClose={restoreAndClose}
      onCancel={(event) => { if (update.isPending) event.preventDefault(); }}
      className="m-auto max-h-[90dvh] w-[min(94vw,60rem)] overflow-y-auto rounded-2xl border border-border bg-background p-0 text-foreground shadow-2xl backdrop:bg-black/60"
    >
      <div className="sticky top-0 z-10 flex items-start justify-between border-b border-border bg-background p-5">
        <div>
          <h2 id="customer-detail-title" className="text-xl font-semibold">Customer details</h2>
          <p className="text-sm text-muted-foreground">Workers, access state and audit history</p>
        </div>
        <Button variant="ghost" size="icon" onClick={close} aria-label="Close customer details"><X className="size-4" /></Button>
      </div>

      <div className="space-y-6 p-5">
        {detail.isLoading && <p role="status" aria-busy="true" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading customer...</p>}
        {detail.isError && (
          <div role="alert" className="rounded-xl border border-destructive/30 p-4 text-sm text-destructive">
            Couldn&apos;t load this customer. <button className="underline" onClick={() => detail.refetch()}>Retry</button>
          </div>
        )}
        {detail.data && (
          <>
            <section className="grid gap-3 sm:grid-cols-4" aria-label="Customer summary">
              <Summary label="Email" value={detail.data.email} />
              <Summary label="Plan" value={detail.data.plan} />
              <Summary label="Revenue" value={`$${(detail.data.earnings_cents / 100).toFixed(2)}`} />
              <div className="rounded-xl border border-border p-3"><p className="text-xs text-muted-foreground">Studio</p><p className="mt-1 text-sm font-semibold">{detail.data.is_studio ? "Enabled" : "Disabled"}</p>{role === "super_admin" && <Button className="mt-2" size="sm" variant="outline" disabled={studioUpdate.isPending} onClick={() => studioUpdate.mutate()}>{detail.data.is_studio ? "Disable Studio" : "Enable Studio"}</Button>}</div>
            </section>
            {studioUpdate.isError && <p role="alert" className="text-sm text-destructive">Studio access update failed. Retry.</p>}

            {role === "viewer" && (
              <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
                Read-only access. Only a super-admin can change worker availability.
              </div>
            )}

            <section aria-labelledby="workers-heading">
              <h3 id="workers-heading" className="mb-3 font-semibold">Workers</h3>
              <div className="space-y-3">
                {detail.data.workers.map((worker) => (
                  <Card key={worker.id}>
                    <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="font-medium">{worker.name}</p>
                        <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                          <span>{worker.type}</span><span>{worker.status}</span>
                          <Badge variant={worker.enabled ? "success" : "muted"}>{worker.enabled ? "Enabled" : "Disabled"}</Badge>
                        </div>
                      </div>
                      {role === "super_admin" && (
                        <Button variant={worker.enabled ? "destructive" : "default"} onClick={(event) => { confirmTrigger.current = event.currentTarget; setConfirmWorker(worker); setReason(""); }}>
                          {worker.enabled ? "Disable worker" : "Enable worker"}
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                ))}
                {detail.data.workers.length === 0 && <p className="text-sm text-muted-foreground">No workers for this customer.</p>}
              </div>
            </section>

            {confirmWorker && (
              <dialog
                ref={confirmDialogRef}
                aria-labelledby="confirm-worker-title"
                aria-describedby="confirm-worker-description"
                onClose={(event) => {
                  event.stopPropagation();
                  restoreConfirmationFocus();
                }}
                onCancel={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  if (!update.isPending) closeConfirmation();
                }}
                className="m-auto w-[min(92vw,30rem)] rounded-xl border border-amber-500/30 bg-background p-5 text-foreground shadow-2xl backdrop:bg-black/60"
              >
                <h3 id="confirm-worker-title" className="font-semibold">Confirm {confirmWorker.enabled ? "disable" : "enable"}</h3>
                <p id="confirm-worker-description" className="mt-1 text-sm text-muted-foreground">{confirmWorker.name} will be {confirmWorker.enabled ? "blocked from new and in-flight execution" : "available for execution again"}.</p>
                <label className="mt-3 block text-sm font-medium">Reason (optional)<Input autoFocus className="mt-1" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} /></label>
                {update.isError && <p role="alert" className="mt-2 text-sm text-destructive">Update failed. Review access and retry.</p>}
                <div className="mt-3 flex justify-end gap-2">
                  <Button variant="outline" disabled={update.isPending} onClick={closeConfirmation}>Cancel</Button>
                  <Button variant={confirmWorker.enabled ? "destructive" : "default"} disabled={update.isPending} onClick={() => update.mutate()}>
                    {update.isPending ? "Updating..." : "Confirm change"}
                  </Button>
                </div>
              </dialog>
            )}

            <section aria-labelledby="audit-heading">
              <h3 id="audit-heading" className="mb-3 font-semibold">Worker audit history</h3>
              <div className="space-y-2">
                {detail.data.worker_state_audit.map((entry) => {
                  const worker = detail.data.workers.find((candidate) => candidate.id === entry.agent_id);
                  return (
                    <div key={entry.id} className="rounded-lg border border-border p-3 text-sm">
                      <p className="font-medium">{worker?.name ?? entry.agent_id}: {entry.previous_enabled ? "Enabled" : "Disabled"} to {entry.enabled ? "Enabled" : "Disabled"}</p>
                      <p className="text-muted-foreground">{entry.changed_by_email} · {new Date(entry.created_at).toLocaleString()}</p>
                      <p className="text-muted-foreground">Reason: {entry.reason || "Not provided"}</p>
                    </div>
                  );
                })}
                {detail.data.worker_state_audit.length === 0 && <p className="text-sm text-muted-foreground">No worker state changes recorded.</p>}
              </div>
            </section>
          </>
        )}
      </div>
    </dialog>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-border p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 truncate text-sm font-semibold">{value}</p></div>;
}
