"use client";

// Chat History view -- reads GET /finance/{agentId}/history and renders the transcript, with a
// clear-history action. Mirrors the History tab of the original financial dashboard.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, MessageSquare, RefreshCw, Trash2 } from "lucide-react";
import { cn } from "@qiko/ui";
import { clearFinanceHistory, getFinanceHistory } from "@/lib/api";
import { formatHistoryTime } from "./utils";

export function FinanceHistoryPanel({ agentId }: { agentId: string }) {
  const qc = useQueryClient();
  const historyQ = useQuery({ queryKey: ["finance-history", agentId], queryFn: () => getFinanceHistory(agentId), retry: false });
  const clear = useMutation({
    mutationFn: () => clearFinanceHistory(agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["finance-history", agentId] }),
  });
  const items = historyQ.data?.history ?? [];

  return (
    <section className="flex h-full flex-col overflow-hidden rounded-2xl border border-white/[0.08]" style={{ background: "oklch(0.15 0.02 250)" }}>
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/[0.06] px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-violet-500/20 text-violet-300"><History className="h-4 w-4" /></span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white/90">Chat History</p>
            <p className="truncate text-[11px] text-white/35">{historyQ.data?.count ?? items.length} messages</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => void historyQ.refetch()} disabled={historyQ.isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] px-2.5 py-1.5 text-[11px] font-medium text-white/50 transition-colors hover:bg-white/[0.06] hover:text-white/80 disabled:opacity-40">
            <RefreshCw className={cn("h-3.5 w-3.5", historyQ.isFetching && "animate-spin")} /> Refresh
          </button>
          {items.length > 0 && (
            <button type="button" onClick={() => clear.mutate()} disabled={clear.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-red-500/20 bg-red-500/10 px-2.5 py-1.5 text-[11px] font-medium text-red-200/90 transition-colors hover:bg-red-500/20 disabled:opacity-40">
              <Trash2 className="h-3.5 w-3.5" /> Clear
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {historyQ.isLoading && <p className="text-sm text-white/45">Loading history…</p>}
        {historyQ.isError && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-200/90">
            {(historyQ.error as Error).message}
          </div>
        )}
        {!historyQ.isLoading && !historyQ.isError && items.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center text-white/45">
            <MessageSquare className="mb-3 h-8 w-8 text-white/25" />
            <p className="text-sm">No conversations yet.</p>
            <p className="mt-1 text-xs">Ask the analyst a question to start a history.</p>
          </div>
        )}
        {items.map((m, i) => (
          <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2.5",
              m.role === "user" ? "rounded-br-sm bg-indigo-500/20 text-white" : "rounded-bl-sm bg-white/[0.05] text-white/85")}>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</p>
              {m.timestamp ? <p className="mt-1 text-[10px] text-white/35">{formatHistoryTime(m.timestamp)}</p> : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
