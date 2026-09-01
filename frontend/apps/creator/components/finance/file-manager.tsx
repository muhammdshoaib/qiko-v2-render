"use client";

// Upload / list / delete the property-portfolio Excel workbooks that power the dashboard. Used both
// inside the empty state (upload CTA) and behind a "Manage files" dialog on the worker info bar.
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Loader2, Trash2, Upload } from "lucide-react";
import { Button, cn, Dialog } from "@qiko/ui";
import {
  Dialog as FileListDialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { deleteFinanceFiles, listFinanceFiles, uploadFinanceFile } from "@/lib/api";

const ACCEPT = ".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function useFinanceFiles(agentId: string) {
  return useQuery({ queryKey: ["finance-files", agentId], queryFn: () => listFinanceFiles(agentId), retry: false });
}

/** Inner body: upload button + file list. Compact variant used in the empty state hides the list header.
 * `onConfirmOpenChange` lets a container dialog (see FinanceFileManagerDialog) know a nested
 * delete-confirmation is open, so it can block its own Escape handling: Radix's Escape listener
 * is a document-level, capture-phase listener, which runs before any bubble-phase handler on the
 * confirmation itself, so nothing the confirmation does on its own `onKeyDown` can stop it. */
export function FinanceFileManager({ agentId, onUploaded, onConfirmOpenChange }: {
  agentId: string; onUploaded?: () => void; onConfirmOpenChange?: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const filesQ = useFinanceFiles(agentId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ id: string; label: string } | null>(null);
  const deleteOpenerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    onConfirmOpenChange?.(!!pendingDelete);
  }, [pendingDelete, onConfirmOpenChange]);

  const upload = useMutation({
    mutationFn: (file: File) => uploadFinanceFile(agentId, file),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["finance-files", agentId] });
      qc.invalidateQueries({ queryKey: ["finance-analytics", agentId] });
      onUploaded?.();
    },
    onError: (err) => setError((err as Error).message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteFinanceFiles(agentId, [id]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance-files", agentId] });
      qc.invalidateQueries({ queryKey: ["finance-analytics", agentId] });
      setPendingDelete(null);
    },
  });

  const requestRemove = (id: string, label: string, opener: HTMLElement | null) => {
    deleteOpenerRef.current = opener;
    setPendingDelete({ id, label });
  };
  const confirmRemove = () => {
    if (!pendingDelete || remove.isPending) return;
    remove.mutate(pendingDelete.id);
  };

  const files = filesQ.data?.files ?? [];

  return (
    <div className="space-y-4">
      <input ref={inputRef} type="file" accept={ACCEPT} className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />

      <button type="button" disabled={upload.isPending} onClick={() => inputRef.current?.click()}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-cyan-400/30 bg-cyan-500/10 px-4 py-3 text-sm font-semibold text-cyan-200 transition-colors hover:bg-cyan-500/20 disabled:opacity-50">
        {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
        {upload.isPending ? "Uploading…" : "Upload .xlsx workbook"}
      </button>

      {error && <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200/90">{error}</p>}

      <div className="space-y-2">
        {filesQ.isLoading && <p className="text-xs text-white/45">Loading files…</p>}
        {!filesQ.isLoading && files.length === 0 && (
          <p className="text-xs text-white/45">No workbooks uploaded yet.</p>
        )}
        {files.map((f) => (
          <div key={f.id} className="flex items-center gap-3 rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 py-2.5">
            <FileSpreadsheet className="h-4 w-4 shrink-0 text-emerald-400" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-white/85">{f.label}</p>
              <p className="text-[10px] text-white/45">{f.rowCount.toLocaleString()} rows</p>
            </div>
            <button type="button" onClick={(e) => requestRemove(f.id, f.label, e.currentTarget)} disabled={remove.isPending}
              className="shrink-0 rounded-md p-1.5 text-white/40 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-40"
              aria-label={`Delete ${f.label}`}>
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      <Dialog
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        opener={deleteOpenerRef.current}
        busy={remove.isPending}
        labelledBy="delete-workbook-title"
      >
        {pendingDelete && (
          <div className="space-y-4">
            <h3 id="delete-workbook-title" className="pr-10 text-lg font-semibold text-white">
              Delete &quot;{pendingDelete.label}&quot;?
            </h3>
            <p className="text-sm text-slate-300">This will remove its data from the dashboard. This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" disabled={remove.isPending} onClick={() => setPendingDelete(null)}>
                Cancel
              </Button>
              <Button type="button" variant="destructive" disabled={remove.isPending} onClick={confirmRemove}>
                {remove.isPending ? "Deleting..." : "Delete"}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}

export function FinanceFileManagerDialog({ agentId, open, onOpenChange, className, onUploaded }: {
  agentId: string; open: boolean; onOpenChange: (v: boolean) => void; className?: string; onUploaded?: () => void;
}) {
  // Radix calls onEscapeKeyDown from within its own capture-phase listener before deciding to
  // dismiss, so this is the only place that can actually stop Escape from closing this dialog
  // while the nested delete-confirmation (a plain native <dialog>, not a Radix one) is open.
  const [confirmOpen, setConfirmOpen] = useState(false);
  return (
    <FileListDialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn("border-white/[0.08] text-white", className)}
        style={{ background: "oklch(0.16 0.02 250)" }}
        onEscapeKeyDown={(e) => { if (confirmOpen) e.preventDefault(); }}
      >
        <DialogHeader>
          <DialogTitle className="text-white/90">Portfolio workbooks</DialogTitle>
          <DialogDescription className="text-white/50">
            Upload Excel workbooks (.xlsx) to power the dashboard. Delete a file to remove its data.
          </DialogDescription>
        </DialogHeader>
        <FinanceFileManager agentId={agentId} onUploaded={onUploaded} onConfirmOpenChange={setConfirmOpen} />
      </DialogContent>
    </FileListDialog>
  );
}
