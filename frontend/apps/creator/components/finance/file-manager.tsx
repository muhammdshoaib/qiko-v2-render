"use client";

// Upload / list / delete the property-portfolio Excel workbooks that power the dashboard. Used both
// inside the empty state (upload CTA) and behind a "Manage files" dialog on the worker info bar.
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Loader2, Trash2, Upload } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  Dialog as FileListDialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useConfirmActionDialog } from "@/components/confirm-action-dialog";
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
  const { openConfirmationDialog, closeConfirmationDialog, setPending, ConfirmActionDialog, isOpen } =
    useConfirmActionDialog();
  const filesQ = useFinanceFiles(agentId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onConfirmOpenChange?.(isOpen);
  }, [isOpen, onConfirmOpenChange]);

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
    },
  });

  const files = filesQ.data?.files ?? [];

  return (
    <div className="space-y-4">
      {ConfirmActionDialog}
      <input ref={inputRef} type="file" accept={ACCEPT} className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />

      <button type="button" disabled={upload.isPending} onClick={() => inputRef.current?.click()}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-indigo-400/30 bg-indigo-600/10 px-4 py-3 text-sm font-semibold text-indigo-700 transition-colors hover:bg-indigo-600/20 disabled:opacity-50">
        {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
        {upload.isPending ? "Uploading…" : "Upload .xlsx workbook"}
      </button>

      {error && <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200/90">{error}</p>}

      <div className="space-y-2">
        {filesQ.isLoading && <p className="text-xs text-slate-400">Loading files…</p>}
        {!filesQ.isLoading && files.length === 0 && (
          <p className="text-xs text-slate-400">No workbooks uploaded yet.</p>
        )}
        {files.map((f) => (
          <div key={f.id} className="flex items-center gap-3 rounded-lg border border-border bg-muted/50 px-3 py-2.5">
            <FileSpreadsheet className="h-4 w-4 shrink-0 text-emerald-700" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-foreground/85">{f.label}</p>
              <p className="text-[10px] text-slate-400">{f.rowCount.toLocaleString()} rows</p>
            </div>
            <button type="button"
              onClick={(e) => openConfirmationDialog({
                title: "Delete workbook?",
                description: `Delete "${f.label}"? Its data will be removed from the dashboard.`,
                confirmLabel: "Delete",
                isDestructive: true,
                onConfirm: () => {
                  setPending(true);
                  remove.mutate(f.id, {
                    onSuccess: () => closeConfirmationDialog(),
                    onSettled: () => setPending(false),
                  });
                },
              }, e.currentTarget)}
              disabled={remove.isPending}
              className="shrink-0 rounded-md p-1.5 text-slate-400 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-40"
              aria-label={`Delete ${f.label}`}>
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export function FinanceFileManagerDialog({ agentId, open, onOpenChange, className, onUploaded }: {
  agentId: string; open: boolean; onOpenChange: (v: boolean) => void; className?: string; onUploaded?: () => void;
}) {
  // Radix calls onEscapeKeyDown from within its own capture-phase listener before deciding to
  // dismiss, so this is the only place that can actually stop Escape from closing this dialog
  // while the nested delete-confirmation (now also a Radix AlertDialog, via
  // useConfirmActionDialog) is open. Kept as defense in depth even though Radix's own
  // dismissable-layer stack may already coordinate correctly between two of its own primitives.
  const [confirmOpen, setConfirmOpen] = useState(false);
  return (
    <FileListDialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn("border-border text-foreground", className)}
        style={{ background: "oklch(0.16 0.02 250)" }}
        onEscapeKeyDown={(e) => { if (confirmOpen) e.preventDefault(); }}
      >
        <DialogHeader>
          <DialogTitle className="text-slate-800">Portfolio workbooks</DialogTitle>
          <DialogDescription className="text-slate-500">
            Upload Excel workbooks (.xlsx) to power the dashboard. Delete a file to remove its data.
          </DialogDescription>
        </DialogHeader>
        <FinanceFileManager agentId={agentId} onUploaded={onUploaded} onConfirmOpenChange={setConfirmOpen} />
      </DialogContent>
    </FileListDialog>
  );
}
