"use client";

// Standalone full-screen cockpit for the Sales Intelligence worker -- deliberately NOT wrapped in
// the generic <AppShell> (no global Creator/Studio left rail): this mirrors the original worker
// product's own top bar + icon nav + chat panel layout pixel-for-pixel (see
// studio-sales-intel-detail.png / pipeline-view.png / ingestion-filters.png / studio-sf-push-log.png).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Bell, LayoutGrid, MessageSquare, Radar, TableProperties, Upload } from "lucide-react";
import { cn } from "@qiko/ui";
import { NotificationBell } from "@/components/cockpit/notification-bell";
import { CockpitChatPanel } from "@/components/cockpit/chat-panel";
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
  // One conversation id per cockpit mount, kept stable across re-renders.
  const [cid] = useState(() => `sales-intel-${agentId}-${Math.random().toString(36).slice(2)}`);

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
          <button onClick={() => router.push("/studio")} className="flex shrink-0 items-center gap-1.5 rounded-md px-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
            <ArrowLeft className="size-4" /> <span className="hidden sm:inline">Studio</span>
          </button>
          <span className="hidden h-4 w-px bg-white/10 sm:block" />
          <span className="hidden size-6 shrink-0 items-center justify-center rounded-md bg-indigo-500/15 text-indigo-400 sm:flex">
            <MessageSquare className="size-3.5" />
          </span>
          <div className="flex min-w-0 flex-col">
            <h1 className="truncate text-sm font-semibold leading-tight text-white">{workerName}</h1>
            <p className="flex items-center gap-1 text-[10px] leading-tight text-slate-500">
              <span className="size-1.5 rounded-full bg-emerald-400" /> IDG Security &middot; Ready
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <NotificationBell category="sales_intelligence" />
          <button onClick={() => setChatOpen((v) => !v)} aria-expanded={chatOpen} aria-label="Toggle chat panel"
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
            <MessageSquare className="size-3.5" /> <span className="hidden sm:inline">Chat</span>
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Desktop side nav (lg+): keeps the original pixel-for-pixel side-by-side layout. */}
        <nav aria-label="Cockpit sections" className="hidden w-[210px] shrink-0 flex-col gap-5 overflow-y-auto border-r border-white/[0.06] px-4 py-5 lg:flex">
          {(["OVERVIEW", "USE CASES"] as const).map((group) => (
            <div key={group}>
              <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{group}</p>
              <div className="flex flex-col gap-1">
                {NAV_ITEMS.filter((n) => n.group === group).map((item) => {
                  const isActive = item.section === active;
                  const Icon = item.icon;
                  return (
                    <button key={item.section} onClick={() => router.push(sectionHref(agentId, item.section))}
                      aria-current={isActive ? "page" : undefined}
                      className={cn("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
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
                  className={cn("flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60",
                    isActive ? "border border-indigo-500/30 bg-indigo-500/10 text-white" : "text-slate-400 hover:bg-white/[0.03] hover:text-white")}>
                  <Icon className={cn("size-3.5 shrink-0", isActive ? "text-indigo-400" : "text-slate-500")} />
                  <span className="whitespace-nowrap">{item.label}</span>
                </button>
              );
            })}
          </nav>

          <main className="min-w-0 flex-1 overflow-y-auto px-4 py-4 lg:px-6 lg:py-6">{children}</main>
        </div>

        {chatOpen && (
          <CockpitChatPanel
            workerName={workerName}
            onClose={() => setChatOpen(false)}
            onAsk={(q) => ask(cid, q, agentId).then((r) => r.text)}
            emptyPrompt="Ask about RFPs, document uploads, or anything in your workflow."
            placeholder="Ask something..."
            inputHint="Enter to send &middot; ask about opportunities, sources or Salesforce pushes"
            errorText={"Sorry, I couldn't answer that just now. Please try again in a moment."}
          />
        )}
      </div>
    </div>
  );
}
