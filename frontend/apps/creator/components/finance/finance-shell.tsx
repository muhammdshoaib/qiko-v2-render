"use client";

import { useMemo, useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { Building2, Calendar, ChevronDown, History, LayoutGrid, MessageSquare, Upload } from "lucide-react";
import { cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { CockpitChatPanel } from "@/components/cockpit/chat-panel";
import { financeChat, getFinanceHistory } from "@/lib/api";
import { FinanceFileManagerDialog } from "@/components/finance/file-manager";
import { FinanceProvider, useFinance } from "./finance-context";
import { monthOptionsFromFiles } from "./utils";

const BG = "oklch(0.13 0.025 250)";

export function FinanceShell({ agentId, children }: { agentId: string; children: React.ReactNode }) {
  return (
    <FinanceProvider agentId={agentId}>
      <FinanceShellInner>{children}</FinanceShellInner>
    </FinanceProvider>
  );
}

function FinanceShellInner({ children }: { children: React.ReactNode }) {
  const { id: agentId } = useParams<{ id: string }>();
  const { workerName, month, setMonth, filesOpen, setFilesOpen, chatOpen, setChatOpen, analytics, files } = useFinance();
  const router = useRouter();
  const pathname = usePathname();
  const [dateOpen, setDateOpen] = useState(false);

  const dashboardHref = `/studio/${agentId}/finance`;
  const historyHref = `/studio/${agentId}/finance/history`;
  const isDashboard = pathname === dashboardHref;
  const isHistory = pathname === historyHref;

  const monthOptions = useMemo(() => monthOptionsFromFiles(files), [files]);
  const selectedLabel = month === "all"
    ? "All"
    : monthOptions.find((o) => o.value === month)?.label ?? month;

  const hasData = (analytics?.properties?.length ?? 0) > 0 || (analytics?.totalRows ?? 0) > 0;

  return (
    <AppShell title="Studio">
      <div className="flex h-[100dvh] flex-col overflow-hidden" style={{ background: BG }}>
        <header className="flex flex-wrap items-center gap-2 border-b border-white/[0.04] px-4 py-2.5 sm:gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-600">
              <Building2 className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white/90">{workerName}</p>
              <p className="text-[10px] text-white/45">Financial Analyst</p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-1 rounded-lg bg-white/[0.04] p-0.5">
            <NavButton active={isDashboard} onClick={() => router.push(dashboardHref)} icon={LayoutGrid} label="Dashboard" />
            <NavButton active={chatOpen} onClick={() => setChatOpen((v) => !v)} icon={MessageSquare} label="Chat" />
            <NavButton active={isHistory} onClick={() => router.push(historyHref)} icon={History} label="History" />
          </div>

          {isDashboard && (
            <div className="flex w-full items-center gap-2 sm:w-auto sm:justify-end">
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setDateOpen((v) => !v)}
                  className="flex h-9 items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 text-xs transition-all hover:bg-white/[0.06]"
                >
                  <Calendar className="h-3.5 w-3.5 text-indigo-400" />
                  <span className="font-medium text-white/80">{selectedLabel}</span>
                  <ChevronDown className={cn("h-3 w-3 text-white/45 transition-transform", dateOpen && "rotate-180")} />
                </button>
                {dateOpen && (
                  <div className="absolute right-0 top-full z-50 mt-1.5 w-56 overflow-hidden rounded-xl border border-white/[0.08] shadow-2xl" style={{ background: "oklch(0.16 0.025 250)" }}>
                    <div className="max-h-64 overflow-y-auto py-1">
                      {[{ value: "all", label: "All" }, ...monthOptions].map((opt) => (
                        <button
                          key={opt.value}
                          onClick={() => { setMonth(opt.value); setDateOpen(false); }}
                          className={cn("flex w-full items-center justify-between px-3 py-2 text-xs transition-colors",
                            opt.value === month ? "bg-indigo-500/10 text-indigo-400" : "text-white/68 hover:bg-white/[0.05] hover:text-white/88")}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={() => setFilesOpen(true)}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 text-xs text-white/82 transition-colors hover:bg-white/[0.06]"
              >
                <Upload className="h-3.5 w-3.5 text-cyan-300" /> Files
              </button>
            </div>
          )}
        </header>

        <div className="flex min-h-0 flex-1 overflow-hidden">
          <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            {children}
          </main>
          {chatOpen && (
            <CockpitChatPanel
              workerName={workerName}
              onClose={() => setChatOpen(false)}
              onAsk={(q) => financeChat(agentId, q).then((r) => r.reply)}
              ready={hasData}
              emptyPrompt="Ask about property performance, vendor costs, profitability, arrears, or risk."
              notReadyTitle="No workbook uploaded"
              notReadyPrompt="Upload a property portfolio workbook to start chatting with the Financial Analyst."
              placeholder="Ask about property performance, vendor costs, profitability…"
              notReadyPlaceholder="Upload a workbook to enable chat"
              inputHint="Grounded in uploaded workbooks"
              errorText="Sorry, I couldn't answer that."
              loadHistory={async () => {
                const res = await getFinanceHistory(agentId);
                return res.history.map((h) => ({ role: h.role, text: h.content }));
              }}
              historyKey={agentId}
            />
          )}
        </div>
      </div>

      <FinanceFileManagerDialog agentId={agentId} open={filesOpen} onOpenChange={setFilesOpen} />
    </AppShell>
  );
}

function NavButton({ active, onClick, icon: Icon, label }: { active: boolean; onClick: () => void; icon: React.ElementType; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn("flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
        active ? "bg-white/[0.12] text-white" : "text-white/50 hover:text-white/75")}
    >
      <Icon className="h-3.5 w-3.5" /> {label}
    </button>
  );
}
