"use client";

// Standalone full-screen cockpit for the Sales Intelligence worker -- deliberately NOT wrapped in
// the generic <AppShell> (no global Creator/Studio left rail): this mirrors the original worker
// product's own top bar + icon nav + chat panel layout pixel-for-pixel (see
// studio-sales-intel-detail.png / pipeline-view.png / ingestion-filters.png / studio-sf-push-log.png).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bell, LayoutGrid, MessageSquare, Radar, Sparkles, TableProperties, Upload, X } from "lucide-react";
import { cn } from "@qiko/ui";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { NotificationBell } from "@/components/sales-intelligence/notification-bell";
import { ask } from "@/lib/api";

export type CockpitSection = "overview" | "pipeline" | "ingestion" | "log" | "notifications";

const NAV_ITEMS: { section: CockpitSection; label: string; sub: string; icon: typeof LayoutGrid; group: "OVERVIEW" | "USE CASES" }[] = [
  { section: "overview", label: "Overview", sub: "DASHBOARD", icon: LayoutGrid, group: "OVERVIEW" },
  { section: "notifications", label: "Notifications", sub: "INBOX", icon: Bell, group: "OVERVIEW" },
  { section: "pipeline", label: "Opportunity Pipeline", sub: "PIPELINE", icon: TableProperties, group: "USE CASES" },
  { section: "ingestion", label: "Ingestion", sub: "SOURCES", icon: Radar, group: "USE CASES" },
  { section: "log", label: "Salesforce Push Log", sub: "LOG", icon: Upload, group: "USE CASES" },
];

function sectionHref(agentId: string, section: CockpitSection): string {
  const base = `/studio/${agentId}/sales-intelligence`;
  if (section === "overview") return base;
  if (section === "log") return `${base}/salesforce-log`;
  return `${base}/${section}`;
}

export function CockpitShell({ agentId, workerName, active, children }: {
  agentId: string; workerName: string; active: CockpitSection; children: React.ReactNode;
}) {
  const router = useRouter();
  const [chatOpen, setChatOpen] = useState(true);

  // On mobile/tablet the chat is a full-height overlay drawer, so don't open it over the content
  // on first load; keep the original open-by-default behaviour on lg+ (inline side column).
  useEffect(() => {
    if (typeof window !== "undefined" && !window.matchMedia("(min-width: 1024px)").matches) {
      setChatOpen(false);
    }
  }, []);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#05070d] text-slate-200">
      <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-white/[0.06] px-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <button onClick={() => router.push("/studio")} className="flex shrink-0 items-center gap-1.5 text-sm text-slate-400 hover:text-white">
            <ArrowLeft className="size-4" /> <span className="hidden sm:inline">Studio</span>
          </button>
          <span className="hidden h-4 w-px bg-white/10 sm:block" />
          <span className="hidden size-6 shrink-0 items-center justify-center rounded-md bg-indigo-500/15 text-indigo-400 sm:flex">
            <MessageSquare className="size-3.5" />
          </span>
          <h1 className="truncate text-sm font-semibold text-white">{workerName}</h1>
          <span className="hidden shrink-0 items-center gap-1.5 rounded-full bg-emerald-400/[0.1] px-2 py-[3px] text-[10px] font-semibold uppercase tracking-wider text-emerald-400 sm:flex">
            <span className="size-1.5 rounded-full bg-emerald-400" /> Active
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <NotificationBell category="sales_intelligence" />
          <button onClick={() => setChatOpen((v) => !v)} aria-expanded={chatOpen} aria-label="Toggle chat panel"
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-400">
            <MessageSquare className="size-3.5" /> Chat
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Desktop side nav (lg+): keeps the original pixel-for-pixel side-by-side layout. */}
        <nav className="hidden w-[210px] shrink-0 flex-col gap-5 overflow-y-auto border-r border-white/[0.06] px-4 py-5 lg:flex">
          {(["OVERVIEW", "USE CASES"] as const).map((group) => (
            <div key={group}>
              <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{group}</p>
              <div className="flex flex-col gap-1">
                {NAV_ITEMS.filter((n) => n.group === group).map((item) => {
                  const isActive = item.section === active;
                  const Icon = item.icon;
                  return (
                    <button key={item.section} onClick={() => router.push(sectionHref(agentId, item.section))}
                      className={cn("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors",
                        isActive ? "border border-indigo-500/30 bg-indigo-500/10 text-white" : "text-slate-400 hover:bg-white/[0.03] hover:text-white")}>
                      <Icon className={cn("size-4 shrink-0", isActive ? "text-indigo-400" : "text-slate-500")} />
                      <span className="flex-1 min-w-0">
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
          {/* Mobile/tablet section nav (< lg): horizontal scrolling pills so narrow screens
              never overflow -- mirrors the finance dashboard's hidden…lg pattern. */}
          <nav aria-label="Sections" className="flex shrink-0 gap-1.5 overflow-x-auto border-b border-white/[0.06] px-3 py-2 lg:hidden">
            {NAV_ITEMS.map((item) => {
              const isActive = item.section === active;
              const Icon = item.icon;
              return (
                <button key={item.section} onClick={() => router.push(sectionHref(agentId, item.section))}
                  aria-current={isActive ? "page" : undefined}
                  className={cn("flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors",
                    isActive ? "border border-indigo-500/30 bg-indigo-500/10 text-white" : "text-slate-400 hover:bg-white/[0.03] hover:text-white")}>
                  <Icon className={cn("size-3.5 shrink-0", isActive ? "text-indigo-400" : "text-slate-500")} />
                  <span className="whitespace-nowrap">{item.label}</span>
                </button>
              );
            })}
          </nav>

          <main className="min-w-0 flex-1 overflow-y-auto px-4 py-4 lg:px-6 lg:py-6">{children}</main>
        </div>

        {chatOpen && <ChatPanel agentId={agentId} workerName={workerName} onClose={() => setChatOpen(false)} />}
      </div>
    </div>
  );
}

function ChatPanel({ agentId, workerName, onClose }: { agentId: string; workerName: string; onClose: () => void }) {
  const [cid] = useState(() => `sales-intel-${agentId}-${Math.random().toString(36).slice(2)}`);
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: (question: string) => ask(cid, question, agentId),
    onMutate: (question) => setMessages((m) => [...m, { role: "user", text: question }]),
    onSuccess: (reply) => setMessages((m) => [...m, { role: "assistant", text: reply.text }]),
  });

  return (
    <>
      {/* Dim backdrop on mobile/tablet where the chat is an overlay drawer, not a fixed column. */}
      <div onClick={onClose} className="fixed inset-0 top-14 z-30 bg-black/50 lg:hidden" aria-hidden="true" />
      <aside
        className={cn(
          "z-40 flex w-[300px] shrink-0 flex-col border-l border-white/[0.06] bg-[#05070d]",
          // < lg: overlay drawer anchored under the header on the right.
          "fixed bottom-0 right-0 top-14 max-w-[86vw]",
          // lg+: revert to the original inline side column.
          "lg:static lg:max-w-none",
        )}
      >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400">
            <MessageSquare className="size-4" />
          </span>
          <div>
            <p className="text-[13px] font-semibold text-white">Chat with {workerName}</p>
            <p className="flex items-center gap-1 text-[11px] text-slate-500">
              <span className="size-1.5 rounded-full bg-emerald-400" /> AI assistant · online
            </p>
          </div>
        </div>
        <button onClick={onClose} aria-label="Close chat" className="text-slate-500 hover:text-white"><X className="size-4" /></button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <span className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-400">
              <Sparkles className="size-6" />
            </span>
            <p className="text-sm font-semibold text-white">Start a conversation</p>
            <p className="mt-1.5 max-w-[220px] text-[12px] leading-relaxed text-slate-500">
              Ask about RFPs, document uploads, section progress, or anything in your workflow.
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

      <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { send.mutate(text); setText(""); } }}
        className="border-t border-white/[0.06] p-3">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2.5">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask something..." aria-label="Chat message"
            className="w-full bg-transparent text-[13px] text-white placeholder:text-slate-500 focus:outline-none" />
          <p className="mt-2 text-[10px] text-slate-600">Enter to send · Shift+Enter for new line</p>
        </div>
      </form>
      </aside>
    </>
  );
}
