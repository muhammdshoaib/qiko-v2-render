"use client";

import { useState } from "react";
import { AlertTriangle, Download, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { exportPackBlob } from "@/lib/api";

type ExportKind = "xlsx" | "docx-clean" | "docx-review";

const EXPORTS: { kind: ExportKind; title: string; description: string; filename: string; icon: typeof FileText; tint: string }[] = [
  { kind: "docx-clean", title: "Client submission (.docx)", description: "Section headings and answer prose only -- the clean copy you send to the buyer.", filename: "submission.docx", icon: FileText, tint: "text-indigo-400 bg-indigo-500/10" },
  { kind: "docx-review", title: "Review draft (.docx)", description: "Annotated: requirement text, confidence/status and KB sources per answer, for internal sign-off.", filename: "review-draft.docx", icon: FileText, tint: "text-violet-300 bg-violet-500/10" },
  { kind: "xlsx", title: "Coverage sheet (.xlsx)", description: "One row per requirement with grounding %, status and blank reviewer columns.", filename: "rfp-coverage.xlsx", icon: FileSpreadsheet, tint: "text-emerald-400 bg-emerald-500/10" },
];

export function ExportTab({ packId }: { packId: string }) {
  const [busy, setBusy] = useState<ExportKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(kind: ExportKind, filename: string) {
    if (busy) return;
    setBusy(kind);
    setError(null);
    try {
      const blob = await exportPackBlob(packId, kind);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-white">
          <Download className="size-4 text-indigo-400" /> Export the response
        </h2>
        <p className="mt-1 max-w-2xl text-[13px] text-slate-400">
          Generates from the latest locked/AI drafts. Locked human answers override the AI draft in every export.
        </p>
      </div>

      {error && (
        <p className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
          <AlertTriangle className="size-4 shrink-0" /> {error}
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {EXPORTS.map((x) => {
          const Icon = x.icon;
          const pending = busy === x.kind;
          return (
            <div key={x.kind} className="flex flex-col rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
              <span className={`flex size-9 items-center justify-center rounded-lg ${x.tint}`}>
                <Icon className="size-4" />
              </span>
              <p className="mt-3 text-[14px] font-semibold text-white">{x.title}</p>
              <p className="mt-1 flex-1 text-[12px] leading-relaxed text-slate-500">{x.description}</p>
              <button
                onClick={() => download(x.kind, x.filename)}
                disabled={!!busy}
                className="mt-4 inline-flex items-center justify-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50"
              >
                {pending ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
                {pending ? "Preparing\u2026" : "Download"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
