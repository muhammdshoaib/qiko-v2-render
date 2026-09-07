"use client";

// Searchable picker for a job's optional Knowledge Base Reference (IDG-1000): restrict this
// tender's answers to ONE document from the worker's knowledge base.
//
// Its own popover rather than a native <select> for the same reason as tender-switcher.tsx: the
// OS-rendered option list opens light-grey on iPad/Safari and clashes with the dark cockpit. No
// combobox dependency is introduced; this app has none, and the filtering is one .filter().
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@qiko/ui";
import { listDocuments, type Doc } from "@/lib/api";

export function KnowledgeReferencePicker({ agentId, value, onChange }: {
  agentId: string;
  /** doc_id of the selected reference, or null for the full knowledge base. */
  value: string | null;
  onChange: (docId: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const docsQ = useQuery({ queryKey: ["documents", agentId], queryFn: () => listDocuments(agentId) });
  const docs: Doc[] = useMemo(() => docsQ.data ?? [], [docsQ.data]);
  const matches = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return needle ? docs.filter((d) => d.doc_id.toLowerCase().includes(needle)) : docs;
  }, [docs, filter]);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    function onPointerDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const select = (docId: string | null) => {
    onChange(docId);
    setOpen(false);
    setFilter("");
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={cn(
          "flex w-full items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] transition-colors",
          "hover:bg-white/[0.06] focus-visible:border-indigo-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
          value ? "text-slate-200" : "text-slate-500",
        )}
      >
        <span className="min-w-0 flex-1 truncate text-left">
          {value ?? "Full knowledge base"}
        </span>
        {value && (
          // A dedicated clear control, because "no reference" is a real choice (the default
          // behaviour), not the absence of one.
          <span
            role="button"
            tabIndex={0}
            aria-label="Clear knowledge base reference"
            onClick={(e) => { e.stopPropagation(); select(null); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); select(null); } }}
            className="shrink-0 rounded p-0.5 text-slate-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
          >
            <X className="size-3.5" />
          </span>
        )}
        <ChevronDown aria-hidden="true" className={cn("size-4 shrink-0 text-slate-500 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1 rounded-lg border border-white/10 bg-[#05070d] p-1 shadow-xl shadow-black/50">
          <div className="flex items-center gap-2 border-b border-white/[0.06] px-2.5 py-2">
            <Search aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />
            <input
              ref={searchRef}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter documents…"
              aria-label="Filter knowledge base documents"
              className="min-w-0 flex-1 bg-transparent text-[13px] text-slate-200 placeholder:text-slate-600 focus:outline-none"
            />
          </div>

          <ul role="listbox" aria-label="Knowledge base documents" className="max-h-[40vh] overflow-y-auto">
            <li role="option" aria-selected={value === null}>
              <button
                type="button"
                onClick={() => select(null)}
                className={cn(
                  "flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                  value === null ? "bg-indigo-500/10 text-white" : "text-slate-300 hover:bg-white/[0.06] hover:text-white",
                )}
              >
                <Check aria-hidden="true" className={cn("mt-0.5 size-4 shrink-0", value === null ? "text-indigo-400" : "text-transparent")} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium">Full knowledge base</span>
                  <span className="block text-[11px] text-slate-500">Answers may draw on every document</span>
                </span>
              </button>
            </li>

            {docsQ.isLoading && (
              <li className="px-2.5 py-3 text-[12px] text-slate-500">Loading documents…</li>
            )}
            {docsQ.isError && (
              <li className="px-2.5 py-3 text-[12px] text-red-300">Couldn&apos;t load documents.</li>
            )}
            {!docsQ.isLoading && !docsQ.isError && matches.length === 0 && (
              <li className="px-2.5 py-3 text-[12px] text-slate-500">
                {docs.length === 0 ? "This worker has no documents yet." : "No documents match that filter."}
              </li>
            )}

            {matches.map((d) => {
              const isActive = d.doc_id === value;
              return (
                <li key={d.doc_id} role="option" aria-selected={isActive}>
                  <button
                    type="button"
                    onClick={() => select(d.doc_id)}
                    className={cn(
                      "flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                      isActive ? "bg-indigo-500/10 text-white" : "text-slate-300 hover:bg-white/[0.06] hover:text-white",
                    )}
                  >
                    <Check aria-hidden="true" className={cn("mt-0.5 size-4 shrink-0", isActive ? "text-indigo-400" : "text-transparent")} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{d.doc_id}</span>
                      <span className="block text-[11px] text-slate-500">
                        {d.chunks} passage{d.chunks === 1 ? "" : "s"}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
