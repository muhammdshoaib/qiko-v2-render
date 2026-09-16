"use client";

// Standalone full-screen cockpit for the Pre-Sales / RFP Writer worker -- mirrors the Sales
// Intelligence cockpit-shell (dark theme, indigo/violet accents, top bar + left icon rail + chat
// panel) for cross-vertical consistency, but is tab-state driven (one route, /studio/[id]/pre-sales)
// rather than route-per-section, because tab + active-tender selection are interdependent state.
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronRight, FileText, LayoutGrid, ListChecks, MessageSquare, Plus, ShieldCheck,
  Upload, Download,
} from "lucide-react";
import { cn } from "@qiko/ui";
import { NotificationBell } from "@/components/cockpit/notification-bell";
import { CockpitChatPanel } from "@/components/cockpit/chat-panel";
import { TenderSwitcher } from "@/components/pre-sales/tender-switcher";
import { askTenderChat, getTenderChatHistory, type RfpPack } from "@/lib/api";

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
  workerName, active, onSelect, packs, activePackId, onSelectPack, activePack, onNewTender, onBack, children,
}: {
  workerName: string;
  active: PreSalesTab;
  onSelect: (tab: PreSalesTab) => void;
  packs: RfpPack[];
  activePackId: string | null;
  onSelectPack: (packId: string) => void;
  activePack: RfpPack | null;
  onNewTender: () => void;
  /** When set, shows a "Back" control that returns to the worker landing (clears the ?pack= param). */
  onBack?: () => void;
  children: React.ReactNode;
}) {
  const router = useRouter();
  // Closed on first load at every width: the chat is an overlay now, not an inline column, so
  // opening it by default would cover the content (and the controls in it) until dismissed. It
  // opens on demand from the Chat button in the top bar.
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-[#05070d] text-slate-200">
      <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-white/[0.06] px-3 sm:px-4">
        {/* Breadcrumb trail so entering an RFP reads as drilling into the same tool (not a new area):
            Studio (routes to /studio) / worker (returns to the worker landing via onBack) / active
            tender. Every segment stays visible so Back always has an obvious destination. */}
        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 sm:gap-2">
          <span className="hidden size-6 shrink-0 items-center justify-center rounded-md bg-indigo-500/15 text-indigo-400 sm:flex">
            <FileText className="size-3.5" />
          </span>
          <button
            onClick={() => router.push("/studio")}
            className="shrink-0 rounded-md px-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
          >
            Studio
          </button>
          <ChevronRight aria-hidden="true" className="size-3.5 shrink-0 text-slate-600" />
          {onBack ? (
            <button
              onClick={onBack}
              aria-label="All RFPs"
              className="max-w-[9rem] shrink-0 truncate rounded-md px-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
              title={workerName}
            >
              {workerName}
            </button>
          ) : (
            <span className="max-w-[9rem] shrink-0 truncate px-1 text-sm text-slate-300" title={workerName}>
              {workerName}
            </span>
          )}
          {activePack && (
            <>
              <ChevronRight aria-hidden="true" className="size-3.5 shrink-0 text-slate-600" />
              <span
                aria-current="page"
                className="min-w-0 flex-1 truncate px-1 text-sm font-semibold text-white"
                title={activePack.title}
              >
                {activePack.title}
              </span>
            </>
          )}
        </nav>

        <div className="flex shrink-0 items-center gap-2">
          {packs.length > 0 && (
            <TenderSwitcher
              className="w-[160px]"
              packs={packs}
              activePackId={activePackId}
              onSelectPack={onSelectPack}
            />
          )}
          <button
            onClick={onNewTender}
            aria-label="Add tender"
            className="flex shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] p-1.5 text-slate-300 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
          >
            <Plus className="size-4" />
          </button>
          <NotificationBell category="pre_sales" />
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

        {chatOpen && (
          <CockpitChatPanel
            workerName={workerName}
            onClose={() => setChatOpen(false)}
            ready={!!activePackId}
            // Per-tender persistence: the transcript is keyed to the active tender and loaded from
            // the server, so closing/refreshing/logging back in restores that tender's history, and
            // switching tenders loads the other tender's conversation (never shared across tenders).
            historyKey={activePackId}
            loadHistory={activePackId ? () => getTenderChatHistory(activePackId) : undefined}
            onAsk={(q) => {
              if (!activePackId) return Promise.reject(new Error("no tender selected"));
              return askTenderChat(activePackId, q).then((r) => r.answer);
            }}
            emptyPrompt="Ask about this tender or your knowledge base. I can help develop and expand answers, grounded in your company documents (for example capabilities, systems, certifications and past performance)."
            notReadyTitle="No tender selected"
            notReadyPrompt="Pick or upload a tender, then ask grounded questions to develop your answers from the tender and your knowledge base."
            placeholder={"Ask to develop an answer\u2026"}
            notReadyPlaceholder={"Select a tender first\u2026"}
            inputHint="Enter to send &middot; grounded in your knowledge base and the tender"
            errorText={"Sorry, I couldn't answer that. Please try again in a moment."}
          />
        )}
      </div>
    </div>
  );
}
