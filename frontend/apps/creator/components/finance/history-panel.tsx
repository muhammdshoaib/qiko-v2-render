"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Clock3, MessageSquare, RefreshCw, Search, User } from "lucide-react";
import { cn } from "@qiko/ui";
import { getFinanceHistory, type FinanceHistoryItem } from "@/lib/api";
import { useFinance } from "./finance-context";

export function FinanceHistoryPanel({ agentId }: { agentId: string }) {
  const { setChatTab } = useFinance();
  const historyQ = useQuery({
    queryKey: ["finance-history", agentId],
    queryFn: () => getFinanceHistory(agentId),
    retry: false,
  });
  const [search, setSearch] = useState("");
  const items = historyQ.data?.history ?? [];

  const conversations = useMemo(() => {
    if (items.length === 0) return [];
    const firstUser = items.find((m) => m.role === "user");
    const last = items[items.length - 1];
    const title = String(firstUser?.content ?? "Portfolio chat").trim().slice(0, 72) || "Portfolio chat";
    return [{
      id: "current",
      title,
      updatedAt: last?.timestamp ?? Date.now(),
      messages: items,
    }];
  }, [items]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(term) || c.messages.some((m) => m.content.toLowerCase().includes(term)));
  }, [conversations, search]);

  const selected = filtered[0] ?? conversations[0];

  return (
    <div className="grid h-full min-h-0 w-full min-w-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[minmax(0,1fr)_400px]">
      <section
        className="flex h-full min-h-0 min-w-0 w-full flex-col overflow-hidden rounded-2xl border border-white/[0.08]"
        style={{ background: "oklch(0.15 0.02 250)" }}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/[0.06] px-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-500/20 text-violet-300">
              <MessageSquare className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-white/90">
                {selected?.title || "Chat History"}
              </p>
              <p className="truncate text-[11px] text-white/35">Worker {agentId}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void historyQ.refetch()}
            disabled={historyQ.isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] px-2.5 py-1.5 text-[11px] font-medium text-white/50 transition-colors hover:bg-white/[0.06] hover:text-white/80 disabled:pointer-events-none disabled:opacity-40"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", historyQ.isFetching && "animate-spin")} />
            Refresh
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          {historyQ.isError && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-200/90">
              {(historyQ.error as Error).message}
            </div>
          )}
          {historyQ.isLoading && conversations.length === 0 && !historyQ.isError && (
            <HistorySkeleton />
          )}
          {!historyQ.isLoading && !historyQ.isError && items.length === 0 && (
            <div className="flex min-h-[12rem] items-center justify-center">
              <div className="w-full max-w-lg rounded-xl border border-white/[0.08] p-8 text-center">
                <p className="mb-1 text-sm text-white/50">No messages yet</p>
                <p className="text-xs text-white/35">Use the Chat tab to ask the analyst - conversations appear here.</p>
              </div>
            </div>
          )}
          {(selected?.messages ?? []).map((row, idx) => (
            <HistoryBubble key={`${row.timestamp}-${idx}`} row={row} />
          ))}
        </div>
      </section>

      <aside
        className="hidden h-full min-h-0 w-full flex-col gap-4 rounded-2xl border border-white/[0.08] p-4 xl:flex"
        style={{ background: "oklch(0.16 0.02 250)" }}
      >
        <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/35" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search chats..."
              className="h-9 w-full rounded-lg border border-white/[0.12] bg-white/[0.03] pl-9 pr-3 text-xs text-white/90 outline-none placeholder:text-white/36 focus:border-indigo-400/45"
            />
          </div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-white/68">History</h4>
          <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-2">
            {filtered.length === 0 ? (
              <p className="rounded-lg border border-white/[0.07] bg-white/[0.02] px-2.5 py-2 text-[11px] text-white/42">
                {search.trim() ? "No chats match your search." : "No chat titles available yet."}
              </p>
            ) : (
              filtered.map((conversation) => (
                <div
                  key={conversation.id}
                  className="w-full rounded-lg border border-indigo-400/35 bg-indigo-500/[0.12] px-2.5 py-2 text-left text-white"
                >
                  <div className="flex items-start gap-2.5">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/[0.05]">
                      <span className="text-xs font-semibold text-white/80">P</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex min-w-0 items-center gap-1.5">
                        <User className="h-3 w-3 shrink-0 text-white/45" />
                        <p className="truncate text-xs font-semibold text-white/90">Portfolio chat</p>
                      </div>
                      <div className="mt-0.5 flex min-w-0 items-center gap-1.5">
                        <Clock3 className="h-3 w-3 shrink-0 text-white/35" />
                        <p className="truncate text-[10px] text-white/52">
                          {formatStamp(conversation.updatedAt)}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setChatTab(true)}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/[0.1] py-2.5 text-xs font-medium text-white/70 transition-colors hover:bg-white/[0.05]"
        >
          <MessageSquare className="h-3.5 w-3.5" />
          Back to Chat
        </button>
      </aside>
    </div>
  );
}

function HistoryBubble({ row }: { row: FinanceHistoryItem }) {
  const isUser = row.role === "user";
  return (
    <div className={cn("flex w-full items-end gap-2.5", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-violet-400/30 bg-violet-500/15">
          <MessageSquare className="h-3.5 w-3.5 text-violet-200" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[min(88%,44rem)] rounded-2xl border px-4 py-3 shadow-sm",
          isUser ? "border-indigo-500/30 bg-indigo-500/[0.14]" : "border-white/[0.08] bg-white/[0.04]",
        )}
      >
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-white/45">
            {isUser ? "You" : "Financial Analyst"}
          </span>
          {row.timestamp ? (
            <span className="tabular-nums text-[10px] text-white/30">{formatStamp(row.timestamp)}</span>
          ) : null}
        </div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/90">{row.content}</p>
      </div>
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-indigo-400/30 bg-indigo-500/15">
          <User className="h-3.5 w-3.5 text-indigo-200" />
        </div>
      )}
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="space-y-3 py-2">
      {Array.from({ length: 4 }).map((_, idx) => (
        <div
          key={idx}
          className={cn(
            "animate-pulse rounded-2xl border border-white/[0.06] px-4 py-3.5",
            idx % 2 === 0 ? "ml-4 mr-0 bg-white/[0.03] sm:ml-10" : "ml-0 mr-4 bg-indigo-500/[0.07] sm:mr-10",
          )}
        >
          <div className="mb-3 flex items-center justify-between">
            <div className="h-2.5 w-16 rounded bg-white/10" />
            <div className="h-2.5 w-24 rounded bg-white/10" />
          </div>
          <div className="space-y-2">
            <div className="h-2.5 w-full rounded bg-white/10" />
            <div className="h-2.5 w-5/6 rounded bg-white/10" />
            <div className="h-2.5 w-2/3 rounded bg-white/10" />
          </div>
        </div>
      ))}
    </div>
  );
}

function formatStamp(timestamp: number) {
  const ms = timestamp > 1e12 ? timestamp : timestamp * 1000;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
