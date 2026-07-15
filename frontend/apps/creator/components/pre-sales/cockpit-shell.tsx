"use client";

// Standalone full-screen cockpit for the Pre-Sales / RFP Writer worker -- mirrors the Sales
// Intelligence cockpit-shell (dark theme, indigo/violet accents, top bar + left icon rail + chat
// panel) for cross-vertical consistency, but is tab-state driven (one route, /studio/[id]/pre-sales)
// rather than route-per-section, because tab + active-tender selection are interdependent state.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import {
  ArrowLeft, ChevronDown, FileText, LayoutGrid, ListChecks, MessageSquare, Plus, ShieldCheck,
  Sparkles, Upload, Download, X,
} from "lucide-react";
import { cn } from "@qiko/ui";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { askBidContext, type RfpPack } from "@/lib/api";
import { formatShortDate } from "@/lib/stringUtils";

export type PreSalesTab = "overview" | "sources" | "brief" | "sections" | "compliance" | "export";

const NAV_ITEMS: { tab: PreSalesTab; label: string; sub: string; icon: typeof LayoutGrid; group: "OVERVIEW" | "TENDER" }[] = [
  { tab: "overview", label: "Overview", sub: "DASHBOARD", icon: LayoutGrid, group: "OVERVIEW" },
  { tab: "sources", label: "Sources", sub: "KNOWLEDGE", icon: Upload, group: "OVERVIEW" },
  { tab: "brief", label: "Tender Brief", sub: "SUMMARY", icon: FileText, group: "TENDER" },
  { tab: "sections", label: "Sections", sub: "RESPONSES", icon: ListChecks, group: "TENDER" },
  { tab: "compliance", label: "Compliance", sub: "CHECKS", icon: ShieldCheck, group: "TENDER" },
  { tab: "export", label: "Export", sub: "DELIVER", icon: Download, group: "TENDER" },
];

export function PreSalesCockpitShell({
  workerName, active, onSelect, packs, activePackId, onSelectPack, activePack, onNewTender, children,
}: {
  workerName: string;
  active: PreSalesTab;
  onSelect: (tab: PreSalesTab) => void;
  packs: RfpPack[];
  activePackId: string | null;
  onSelectPack: (packId: string) => void;
  activePack: RfpPack | null;
  onNewTender: () => void;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches) {
      setChatOpen(true);
    }
  }, []);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#05070d] text-slate-200">
      <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-white/[0.06] px-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <button onClick={() => router.push("/studio")} className="flex shrink-0 items-center gap-1.5 rounded-md px-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
            <ArrowLeft className="size-4" /> <span className="hidden sm:inline">Studio</span>
          </button>
          <span className="hidden h-4 w-px bg-white/10 sm:block" />
          <span className="hidden size-6 shrink-0 items-center justify-center rounded-md bg-indigo-500/15 text-indigo-400 sm:flex">
            <FileText className="size-3.5" />
          </span>
          <div className="flex min-w-0 flex-col">
            <h1 className="truncate text-sm font-semibold leading-tight text-white">{workerName}</h1>
            <p className="flex items-center gap-1 text-[10px] leading-tight text-slate-500">
              <span className="size-1.5 rounded-full bg-emerald-400" /> IDG Security &middot; Ready
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {activePack && (
            <div className="hidden min-w-0 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.02] px-2.5 py-1 sm:flex">
              <span className="truncate text-[12px] font-medium text-white" title={activePack.title}>
                {activePack.title}
              </span>
              <span className="text-[11px] text-slate-500">
                &middot; Due {formatShortDate(activePack.deadline)}
              </span>
            </div>
          )}
          {packs.length > 0 && (
            <div className="relative">
              <label htmlFor="tender-switch" className="sr-only">Active tender</label>
              <select
                id="tender-switch"
                value={activePackId ?? ""}
                onChange={(e) => onSelectPack(e.target.value)}
                className="max-w-[160px] appearance-none rounded-lg border border-white/10 bg-white/[0.03] py-1.5 pl-2.5 pr-7 text-[12px] font-medium text-slate-200 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/40"
              >
                {packs.map((p) => (
                  <option key={p.id} value={p.id} className="bg-[#0b0e16] text-slate-200">{p.title}</option>
                ))}
              </select>
              <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-slate-500" />
            </div>
          )}
          <button
            onClick={onNewTender}
            aria-label="Add tender"
            className="flex shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] p-1.5 text-slate-300 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
          >
            <Plus className="size-4" />
          </button>
          <button
            onClick={() => setChatOpen((v) => !v)}
            aria-expanded={chatOpen}
            aria-label="Toggle chat panel"
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
          >
            <MessageSquare className="size-3.5" /> <span className="hidden sm:inline">Chat</span>
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <nav aria-label="Cockpit sections" className="hidden w-[210px] shrink-0 flex-col gap-5 overflow-y-auto border-r border-white/[0.06] px-4 py-5 lg:flex">
          {(["OVERVIEW", "TENDER"] as const).map((group) => (
            <div key={group}>
              <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{group}</p>
              <div className="flex flex-col gap-1">
                {NAV_ITEMS.filter((n) => n.group === group).map((item) => {
                  const isActive = item.tab === active;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.tab}
                      onClick={() => onSelect(item.tab)}
                      aria-current={isActive ? "page" : undefined}
                      className={cn("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                        isActive ? "border border-indigo-500/30 bg-indigo-500/10 text-white" : "text-slate-400 hover:bg-white/[0.03] hover:text-white")}
                    >
                      <Icon className={cn("size-4 shrink-0", isActive ? "text-indigo-400" : "text-slate-500")} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium">{item.label}</span>
                        <span className="block text-[10px] uppercase tracking-wider text-slate-500">{item.sub}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          <nav aria-label="Sections" className="flex shrink-0 gap-1.5 overflow-x-auto border-b border-white/[0.06] px-3 py-2 lg:hidden">
            {NAV_ITEMS.map((item) => {
              const isActive = item.tab === active;
              const Icon = item.icon;
              return (
                <button
                  key={item.tab}
                  onClick={() => onSelect(item.tab)}
                  aria-current={isActive ? "page" : undefined}
                  className={cn("flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                    isActive ? "border border-indigo-500/30 bg-indigo-500/10 text-white" : "text-slate-400 hover:bg-white/[0.03] hover:text-white")}
                >
                  <Icon className={cn("size-3.5 shrink-0", isActive ? "text-indigo-400" : "text-slate-500")} />
                  <span className="whitespace-nowrap">{item.label}</span>
                </button>
              );
            })}
          </nav>

          <main className="min-w-0 flex-1 overflow-y-auto px-4 py-4 lg:px-6 lg:py-6">{children}</main>
        </div>

        {chatOpen && <ChatPanel workerName={workerName} packId={activePackId} onClose={() => setChatOpen(false)} />}
      </div>
    </div>
  );
}

function ChatPanel({ workerName, packId, onClose }: { workerName: string; packId: string | null; onClose: () => void }) {
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: (question: string) => {
      if (!packId) return Promise.reject(new Error("no tender selected"));
      return askBidContext(packId, question);
    },
    onMutate: (question) => setMessages((m) => [...m, { role: "user", text: question }]),
    onSuccess: (reply) => setMessages((m) => [...m, { role: "assistant", text: reply.answer }]),
    onError: () => setMessages((m) => [...m, { role: "assistant", text: "Sorry -- I couldn't answer that. Make sure a tender document has been uploaded, then try again." }]),
  });

  return (
    <>
      <div onClick={onClose} className="fixed inset-0 top-14 z-30 bg-black/50 lg:hidden" aria-hidden="true" />
      <aside
        className={cn(
          "z-40 flex w-[300px] shrink-0 flex-col border-l border-white/[0.06] bg-[#05070d]",
          "fixed bottom-0 right-0 top-14 max-w-[86vw]",
          "lg:static lg:max-w-none",
        )}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400">
              <MessageSquare className="size-4" />
            </span>
            <div>
              <p className="text-[13px] font-semibold text-white">Ask {workerName}</p>
              <p className="flex items-center gap-1 text-[11px] text-slate-500">
                <span className="size-1.5 rounded-full bg-emerald-400" /> Grounded in this tender
              </p>
            </div>
          </div>
          <button onClick={onClose} aria-label="Close chat" className="rounded-md text-slate-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
            <X className="size-4" />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {!packId ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <span className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-400">
                <Sparkles className="size-6" />
              </span>
              <p className="text-sm font-semibold text-white">No tender selected</p>
              <p className="mt-1.5 max-w-[220px] text-[12px] leading-relaxed text-slate-500">
                Pick or upload a tender to ask grounded questions about its scope, rules and deadlines.
              </p>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <span className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-400">
                <Sparkles className="size-6" />
              </span>
              <p className="text-sm font-semibold text-white">Ask about this tender</p>
              <p className="mt-1.5 max-w-[220px] text-[12px] leading-relaxed text-slate-500">
                Scope, submission format, deadlines, qualification rules -- answered only from the tender document.
              </p>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <ChatBubble role={m.role} text={m.text} />
              </div>
            ))
          )}
          {send.isPending && <div className="flex justify-start"><TypingIndicator /></div>}
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); const q = text.trim(); if (q && packId && !send.isPending) { send.mutate(q); setText(""); } }}
          className="border-t border-white/[0.06] p-3"
        >
          <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2.5 focus-within:border-indigo-500/50">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={packId ? "Ask about this tender\u2026" : "Select a tender first\u2026"}
              aria-label="Chat message"
              disabled={!packId || send.isPending}
              className="w-full bg-transparent text-[13px] text-white placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
            />
            <p className="mt-2 text-[10px] text-slate-600">Enter to send &middot; answers cite the tender document</p>
          </div>
        </form>
      </aside>
    </>
  );
}
