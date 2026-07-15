"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FileText, Library, Loader2, Trash2, Upload } from "lucide-react";
import { deleteDocument, ingestFile, listDocuments, type Doc } from "@/lib/api";

export function SourcesTab() {
  const qc = useQueryClient();
  const docsQ = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => ingestFile(file.name.replace(/\.[^.]+$/, "") || file.name, file),
    onSuccess: () => { setError(null); qc.invalidateQueries({ queryKey: ["documents"] }); },
    onError: (e) => setError(e instanceof Error ? e.message : "Upload failed"),
  });

  const remove = useMutation({
    mutationFn: (docId: string) => deleteDocument(docId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });

  const docs: Doc[] = docsQ.data ?? [];

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 text-[15px] font-semibold text-white">
              <Library className="size-4 text-indigo-400" /> Knowledge sources
            </h2>
            <p className="mt-1 max-w-2xl text-[13px] text-slate-400">
              Real IDG documents the AI grounds every answer in -- capability statements, past bids,
              policies and certifications. Uploads are chunked and indexed for citation.
            </p>
          </div>
          <div className="shrink-0">
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              aria-label="Upload knowledge document"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={upload.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50"
            >
              {upload.isPending ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
              {upload.isPending ? "Uploading\u2026" : "Upload document"}
            </button>
          </div>
        </div>

        {error && (
          <p className="mt-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-300">
            <AlertTriangle className="size-3.5 shrink-0" /> {error}
          </p>
        )}
      </div>

      <div className="rounded-2xl border border-white/[0.06]">
        <div className="border-b border-white/[0.06] px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Indexed documents{docs.length ? ` (${docs.length})` : ""}
        </div>
        {docsQ.isLoading ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2].map((i) => <div key={i} className="h-12 animate-pulse rounded-lg bg-white/[0.04]" />)}
          </div>
        ) : docsQ.isError ? (
          <p className="flex items-center gap-2 px-4 py-8 text-sm text-red-300">
            <AlertTriangle className="size-4" /> Couldn&apos;t load documents. Try refreshing.
          </p>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center px-4 py-12 text-center">
            <span className="mb-3 flex size-11 items-center justify-center rounded-2xl bg-white/[0.04] text-slate-500">
              <Library className="size-5" />
            </span>
            <p className="text-sm font-medium text-slate-300">No documents yet</p>
            <p className="mt-1 max-w-sm text-[12px] text-slate-500">
              Upload IDG capability statements and past responses so the AI can cite them when drafting.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-white/[0.04]">
            {docs.map((d) => (
              <li key={d.doc_id} className="flex items-center gap-3 px-4 py-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/[0.04] text-slate-400">
                  <FileText className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-white">{d.doc_id}</p>
                  <p className="text-[11px] text-slate-500">{d.chunks} chunk{d.chunks === 1 ? "" : "s"} indexed</p>
                </div>
                <button
                  onClick={() => remove.mutate(d.doc_id)}
                  disabled={remove.isPending}
                  aria-label={`Delete ${d.doc_id}`}
                  className="rounded-md p-1.5 text-slate-500 hover:bg-red-500/10 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50 disabled:opacity-50"
                >
                  {remove.isPending && remove.variables === d.doc_id ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
