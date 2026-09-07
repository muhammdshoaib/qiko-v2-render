"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FileUp, Loader2, Sparkles, X } from "lucide-react";
import { createRfpPack, extractPack } from "@/lib/api";
import { Input } from "@/components/cockpit/controls";
import { KnowledgeReferencePicker } from "@/components/pre-sales/knowledge-reference-picker";

// Create a tender pack and immediately extract its sections/questions from an uploaded RFP. Used
// both as the empty state (no packs yet) and the "Add tender" flow from the cockpit header.
export function NewTenderPanel({ agentId, onCreated, onCancel }: {
  agentId: string; onCreated: (packId: string) => void; onCancel?: () => void;
}) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [buyer, setBuyer] = useState("");
  const [deadline, setDeadline] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  // Optional. null means the full knowledge base, which is the existing behaviour.
  const [referenceDocId, setReferenceDocId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: async () => {
      const pack = await createRfpPack(agentId, title.trim(), buyer.trim(), deadline || null);
      if (files.length > 0) await extractPack(pack.id, files, referenceDocId);
      return pack;
    },
    onSuccess: (pack) => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["rfp-packs", agentId] });
      onCreated(pack.id);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "Couldn't create the tender"),
  });

  const canSubmit = title.trim().length > 0 && files.length > 0 && !create.isPending;

  return (
    <div className="mx-auto max-w-xl">
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <span className="flex size-10 items-center justify-center rounded-xl bg-indigo-500/15 text-indigo-400">
              <Sparkles className="size-5" />
            </span>
            <div>
              <h2 className="text-[15px] font-semibold text-white">New tender</h2>
              <p className="text-[12px] text-slate-500">Upload an RFP and we&apos;ll parse it into sections and questions.</p>
            </div>
          </div>
          {onCancel && (
            <button onClick={onCancel} aria-label="Cancel" className="rounded-md text-slate-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
              <X className="size-4" />
            </button>
          )}
        </div>

        <form
          className="mt-5 space-y-4"
          onSubmit={(e) => { e.preventDefault(); if (canSubmit) create.mutate(); }}
        >
          <div>
            <label htmlFor="tender-title" className="mb-1 block text-[12px] font-medium text-slate-300">Tender title</label>
            <Input
              id="tender-title" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. UNRWA Physical Security Services"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="tender-buyer" className="mb-1 block text-[12px] font-medium text-slate-300">Buyer <span className="text-slate-500">(optional)</span></label>
              <Input
                id="tender-buyer" value={buyer} onChange={(e) => setBuyer(e.target.value)}
                placeholder="e.g. United Nations"
              />
            </div>
            <div>
              <label htmlFor="tender-deadline" className="mb-1 block text-[12px] font-medium text-slate-300">Deadline <span className="text-slate-500">(optional)</span></label>
              <Input
                id="tender-deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)}
                className="[color-scheme:dark]"
              />
            </div>
          </div>

          <div>
            <span className="mb-1 block text-[12px] font-medium text-slate-300">RFP documents</span>
            <input
              ref={fileRef} type="file" multiple className="hidden" aria-label="RFP documents"
              onChange={(e) => { setFiles(e.target.files ? Array.from(e.target.files) : []); }}
            />
            <button
              type="button" onClick={() => fileRef.current?.click()}
              className="flex w-full items-center gap-2 rounded-lg border border-dashed border-white/15 bg-white/[0.02] px-3 py-3 text-left text-[13px] text-slate-300 hover:border-indigo-500/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
            >
              <FileUp className="size-4 shrink-0 text-slate-500" />
              <span className="min-w-0 flex-1 truncate">
                {files.length === 0
                  ? "Choose PDF, DOCX or text files\u2026"
                  : files.length === 1
                    ? files[0].name
                    : `${files.length} files selected`}
              </span>
            </button>
            {files.length > 0 && (
              <ul className="mt-2 space-y-1">
                {files.map((f, i) => (
                  <li key={`${f.name}-${i}`} className="flex items-center gap-1.5 text-[12px] text-slate-400">
                    <FileUp className="size-3 shrink-0 text-slate-600" />
                    <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <label className="mb-1 block text-[12px] font-medium text-slate-300">
              Knowledge Base Reference <span className="text-slate-500">(optional)</span>
            </label>
            <KnowledgeReferencePicker
              agentId={agentId} value={referenceDocId} onChange={setReferenceDocId}
            />
            <p className="mt-1.5 text-[11px] text-slate-500">
              {referenceDocId
                ? "Answers for this tender will come only from this document. Nothing else in the knowledge base will be used."
                : "Answers will draw on the whole knowledge base. Pick a document to restrict them to a single past response."}
            </p>
          </div>

          {error && (
            <p className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-300">
              <AlertTriangle className="size-3.5 shrink-0" /> {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            {onCancel && (
              <button type="button" onClick={onCancel}
                className="rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-2 text-[13px] font-medium text-slate-200 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
                Cancel
              </button>
            )}
            <button type="submit" disabled={!canSubmit}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
              {create.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              {create.isPending ? "Parsing tender\u2026" : "Create & parse"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
