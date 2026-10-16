"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Database, Library, Loader2, Trash2, Upload } from "lucide-react";
import { deleteDocument, ingestFile, listDocuments, type Doc } from "@/lib/api";
import { OutcomesStrip, type OutcomeTile } from "@/components/cockpit/outcomes-strip";
import { useConfirmActionDialog } from "@/components/confirm-action-dialog";

export function SourcesTab({ agentId }: { agentId: string }) {
  const qc = useQueryClient();
  const { openConfirmationDialog, closeConfirmationDialog, setPending, ConfirmActionDialog } = useConfirmActionDialog();
  const docsQ = useQuery({ queryKey: ["documents", agentId], queryFn: () => listDocuments(agentId) });
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["documents", agentId] });

  const ingest = useMutation({
    // doc_id is the filename without extension, mirroring the validated idg ingest flow. Scoped to
    // this worker (agentId) so its knowledge stays its own (QIK-315).
    mutationFn: (f: File) => ingestFile(f.name.replace(/\.[^.]+$/, "") || f.name, f, agentId),
    onSuccess: () => { setError(null); setFile(null); invalidate(); },
    onError: (e) => setError(e instanceof Error ? e.message : "Ingest failed"),
  });

  const remove = useMutation({
    mutationFn: (docId: string) => deleteDocument(docId, agentId),
    onSuccess: () => { setError(null); invalidate(); },
    onError: (e) => setError(e instanceof Error ? e.message : "Couldn't remove that document"),
  });

  const docs: Doc[] = docsQ.data ?? [];
  // idg metric cards, live from the index:
  //  - Documents ingested / Source families = one per returned document (no server-side grouping yet)
  //  - Passages indexed = total chunks across every document (what search actually retrieves over)
  //  - Embeddings = "local" (embeddings are computed in-tenant, never sent out)
  const passages = useMemo(() => docs.reduce((n, d) => n + d.chunks, 0), [docs]);
  const tiles: OutcomeTile[] = [
    { value: String(docs.length), label: "Documents ingested", caption: "IDG past bids + company docs", trend: "up" },
    { value: String(passages), label: "Passages indexed", caption: "searchable" },
    { value: String(docs.length), label: "Source families", caption: "in the knowledge base" },
    { value: "local", label: "Embeddings", caption: "private" },
  ];

  return (
    <div className="space-y-6">
      {ConfirmActionDialog}
      <OutcomesStrip title="SOURCES" tiles={tiles} />

      <div>
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-foreground">
          <Library className="size-4 text-indigo-400" /> Sources &amp; Ingestion
        </h2>
        <p className="mt-1 max-w-2xl text-[13px] text-slate-400">
          The knowledge base the worker answers from, live from the index. Add documents to ingest
          (extract, chunk, embed) and they appear here immediately.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-muted/40 p-5">
        <p className="text-[13px] font-semibold text-foreground">Add documents</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-muted px-3.5 py-2 text-[13px] font-medium text-slate-700 hover:bg-muted focus-within:ring-2 focus-within:ring-indigo-500">
            <Upload className="size-4" /> Choose file
            <input
              type="file"
              accept=".pdf,.docx,.pptx,.txt,.md"
              className="hidden"
              aria-label="Choose knowledge document"
              onChange={(e) => { setError(null); setFile(e.target.files?.[0] ?? null); e.target.value = ""; }}
            />
          </label>
          <span className="min-w-0 flex-1 truncate text-[12px] text-slate-500">{file?.name ?? "No file chosen"}</span>
          <button
            onClick={() => file && ingest.mutate(file)}
            disabled={!file || ingest.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50"
          >
            {ingest.isPending ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
            {ingest.isPending ? "Ingesting\u2026" : "Ingest"}
          </button>
        </div>
        {error && (
          <p className="mt-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-300">
            <AlertTriangle className="size-3.5 shrink-0" /> {error}
          </p>
        )}
      </div>

      {docsQ.isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-20 animate-pulse rounded-2xl bg-muted" />)}
        </div>
      ) : docsQ.isError ? (
        <p className="flex items-center gap-2 rounded-2xl border border-red-500/20 bg-red-500/[0.06] px-4 py-8 text-sm text-red-300">
          <AlertTriangle className="size-4" /> Couldn&apos;t load documents. Try refreshing.
        </p>
      ) : docs.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-border bg-muted/40 px-4 py-12 text-center">
          <span className="mb-3 flex size-11 items-center justify-center rounded-2xl bg-muted text-slate-500">
            <Database className="size-5" />
          </span>
          <p className="text-sm font-medium text-slate-600">Knowledge base is empty</p>
          <p className="mt-1 max-w-sm text-[12px] text-slate-500">
            Add IDG capability statements and past responses above so the worker can cite them when drafting.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {docs.map((d) => (
            <div key={d.doc_id} className="flex items-start justify-between gap-3 rounded-2xl border border-border bg-muted/40 p-4">
              <div className="min-w-0">
                <p className="truncate text-[13px] font-semibold text-foreground">{d.doc_id}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">IDG knowledge base</p>
                <p className="mt-2 text-[12px] text-slate-400">{d.chunks} passage{d.chunks === 1 ? "" : "s"}</p>
              </div>
              <button
                onClick={(e) => openConfirmationDialog({
                  title: "Remove from knowledge base?",
                  description: `Remove "${d.doc_id}" from the knowledge base?`,
                  confirmLabel: "Remove",
                  isDestructive: true,
                  onConfirm: () => {
                    setPending(true);
                    remove.mutate(d.doc_id, {
                      onSuccess: () => closeConfirmationDialog(),
                      onSettled: () => setPending(false),
                    });
                  },
                }, e.currentTarget)}
                disabled={remove.isPending && remove.variables === d.doc_id}
                aria-label={`Delete ${d.doc_id}`}
                className="shrink-0 rounded-md p-1.5 text-slate-500 hover:bg-red-500/10 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50 disabled:opacity-50"
              >
                {remove.isPending && remove.variables === d.doc_id ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
