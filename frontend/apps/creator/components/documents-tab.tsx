"use client";

import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, Loader2, Trash2, Upload, XCircle } from "lucide-react";
import { Badge, Button, cn, Dialog } from "@qiko/ui";
import { deleteIntelligenceDocument, listIntelligenceDocuments, uploadIntelligenceDocument, type IntelligenceDocument } from "@/lib/api";

const SUPPORTED = new Set(["txt", "md", "csv", "json", "jsonl", "pdf", "docx", "xlsx", "pptx", "html", "htm"]);

export function DocumentsTab({ agentId }: { agentId: string }) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ id: string; filename: string } | null>(null);
  const deleteOpenerRef = useRef<HTMLElement | null>(null);

  const docs = useQuery({
    queryKey: ["intelligence-documents", agentId],
    queryFn: () => listIntelligenceDocuments(agentId),
  });

  const upload = useMutation({
    mutationFn: (file: File) => uploadIntelligenceDocument(agentId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["intelligence-documents", agentId] });
      setError(null);
      if (inputRef.current) inputRef.current.value = "";
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Upload failed"),
  });

  const remove = useMutation({
    mutationFn: (docId: string) => deleteIntelligenceDocument(agentId, docId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["intelligence-documents", agentId] });
      setPendingDelete(null);
    },
  });

  const requestRemove = (id: string, filename: string, opener: HTMLElement | null) => {
    deleteOpenerRef.current = opener;
    setPendingDelete({ id, filename });
  };
  const confirmRemove = () => {
    if (!pendingDelete || remove.isPending) return;
    remove.mutate(pendingDelete.id);
  };

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!SUPPORTED.has(ext)) {
      setError(`${ext ? `.${ext}` : "This"} files are not supported. Try ${Array.from(SUPPORTED).join(", ")}.`);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    setError(null);
    upload.mutate(file);
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Documents</h2>
        <p className="text-sm text-muted-foreground">
          Upload files this worker should use as evidence. Parsing and ingestion run in the background.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          accept={Array.from(SUPPORTED).map((e) => `.${e}`).join(",")}
          onChange={onChange}
          disabled={upload.isPending}
          className="hidden"
        />
        <Button
          variant="secondary"
          onClick={() => inputRef.current?.click()}
          disabled={upload.isPending}
        >
          {upload.isPending ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Upload className="mr-2 size-4" />}
          Upload document
        </Button>
        {upload.isPending && <span className="text-sm text-muted-foreground">Uploading...</span>}
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          <XCircle className="mt-0.5 size-4 shrink-0" />
          {error}
        </div>
      )}

      {docs.isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading documents...
        </div>
      )}
      {docs.isError && <p className="text-sm text-destructive">Could not load documents.</p>}

      {docs.data && docs.data.length === 0 && !docs.isLoading && (
        <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
      )}

      {docs.data && docs.data.length > 0 && (
        <div className="divide-y divide-border rounded-lg border border-border bg-card">
          {docs.data.map((doc) => (
            <DocumentRow key={doc.doc_id} doc={doc}
              onDelete={(opener) => requestRemove(doc.doc_id, doc.filename, opener)} deleting={remove.isPending} />
          ))}
        </div>
      )}

      <Dialog
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        opener={deleteOpenerRef.current}
        busy={remove.isPending}
        labelledBy="delete-document-title"
      >
        {pendingDelete && (
          <div className="space-y-4">
            <h3 id="delete-document-title" className="pr-10 text-lg font-semibold text-foreground">
              Delete &quot;{pendingDelete.filename}&quot;?
            </h3>
            <p className="text-sm text-muted-foreground">This cannot be undone.</p>
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

function DocumentRow({ doc, onDelete, deleting }: { doc: IntelligenceDocument; onDelete: (opener: HTMLElement | null) => void; deleting: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 p-4">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted">
          <FileText className="size-5 text-foreground" />
        </span>
        <div className="min-w-0">
          <p className="truncate font-medium text-foreground">{doc.filename}</p>
          <p className="text-xs text-muted-foreground">{formatBytes(doc.size)} · updated {new Date(doc.updated_at).toLocaleString()}</p>
          {doc.error_message && <p className="mt-1 text-xs text-destructive">{doc.error_message}</p>}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge variant={statusVariant(doc.status)}>{doc.status}</Badge>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Delete document"
          disabled={deleting || doc.status === "uploading"}
          onClick={(e) => onDelete(e.currentTarget)}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
    </div>
  );
}

function statusVariant(status: string) {
  if (status === "ready") return "success";
  if (status === "error") return "destructive";
  return "muted";
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}
