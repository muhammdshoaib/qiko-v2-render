"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import {
  BarChart3, Building2, Calendar, Check, ChevronDown, History, MessageSquare, Search, Upload,
} from "lucide-react";
import { cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { FinanceChatPanel } from "@/components/finance/chat-panel";
import { FinanceFileManagerDialog } from "@/components/finance/file-manager";
import { FinanceProvider, useFinance } from "./finance-context";
import { InsightRail } from "./insight-rail";
import {
  activeProperties, monthOptionsFromAvailableMonths, normalizeFinanceSummary, trendSections, vendorRows,
} from "./utils";

const PAGE_BG = "oklch(0.13 0.025 250)";
const PANEL_BG = "oklch(0.16 0.025 250)";

export function FinanceShell({ agentId, children }: { agentId: string; children: React.ReactNode }) {
  return (
    <FinanceProvider agentId={agentId}>
      <FinanceShellInner>{children}</FinanceShellInner>
    </FinanceProvider>
  );
}

function FinanceShellInner({ children }: { children: React.ReactNode }) {
  const { id: agentId } = useParams<{ id: string }>();
  const {
    workerName, month, setMonth, filesOpen, setFilesOpen, analytics, availableMonths,
    search, setSearch, pendingPrompt, setPendingPrompt, chatTab, setChatTab,
  } = useFinance();
  const router = useRouter();
  const pathname = usePathname();
  const [dateOpen, setDateOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [mobileTrendsOpen, setMobileTrendsOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const dateRef = useRef<HTMLDivElement>(null);

  const dashboardHref = `/studio/${agentId}/finance`;
  const historyHref = `/studio/${agentId}/finance/history`;
  const isHistory = pathname === historyHref;
  const isDashboard = pathname === dashboardHref;
  const tab = chatTab ? "chat" : isHistory ? "history" : "feed";

  const summary = useMemo(() => normalizeFinanceSummary(analytics?.summary), [analytics]);
  const propertyCount = summary.propertyCount || activeProperties(analytics).length;
  const vendorCount = summary.vendorCount || vendorRows(analytics).length;
  const sections = useMemo(() => trendSections(analytics?.trends), [analytics]);
  const monthOptions = useMemo(() => monthOptionsFromAvailableMonths(availableMonths).filter((o) => o.value !== "all"), [availableMonths]);
  const monthsByYear = useMemo(() => {
    const grouped: Record<string, { label: string; value: string }[]> = {};
    for (const opt of monthOptions) {
      const year = opt.value.slice(0, 4) || "Other";
      (grouped[year] ??= []).push(opt);
    }
    return grouped;
  }, [monthOptions]);
  const selectedLabel = month === "all"
    ? (monthOptions.length ? "All time" : "All")
    : monthOptions.find((o) => o.value === month)?.label ?? month;

  const suggestions = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return [];
    const out: { id: string; title: string; subtitle: string; href: string }[] = [];
    for (const p of activeProperties(analytics)) {
      const title = p.name || p.propertyRef || p.propertyId || "Property";
      const ref = p.propertyRef || p.propertyId || title;
      if (title.toLowerCase().includes(term) || String(ref).toLowerCase().includes(term)) {
        out.push({
          id: `p-${ref}`,
          title,
          subtitle: "Property",
          href: `/studio/${agentId}/finance/property/${encodeURIComponent(String(ref))}`,
        });
      }
    }
    for (const v of vendorRows(analytics)) {
      if (v.name.toLowerCase().includes(term)) {
        out.push({
          id: `v-${v.name}`,
          title: v.name,
          subtitle: "Vendor",
          href: `/studio/${agentId}/finance/vendor/${encodeURIComponent(v.name)}`,
        });
      }
    }
    return out.slice(0, 12);
  }, [analytics, search, agentId]);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      const target = event.target as Node;
      if (searchRef.current && !searchRef.current.contains(target)) setSearchOpen(false);
      if (dateRef.current && !dateRef.current.contains(target)) setDateOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function goFeed() {
    setChatTab(false);
    if (!isDashboard) router.push(dashboardHref);
  }
  function goChat() {
    setChatTab(true);
  }
  function goHistory() {
    setChatTab(false);
    if (!isHistory) router.push(historyHref);
  }

  return (
    <AppShell title="Studio">
      <div className="flex h-[100dvh] min-w-0 w-full flex-col overflow-hidden" style={{ background: PAGE_BG }}>
        <header className="flex items-center justify-end border-b border-white/[0.06] px-4 py-3">
          <div className="flex items-center gap-1 rounded-full bg-white/[0.06] p-0.5">
            <TabButton active={tab === "feed"} onClick={goFeed} icon={BarChart3} label="Intelligence" />
            <TabButton active={tab === "chat"} onClick={goChat} icon={MessageSquare} label="Chat" />
            <TabButton active={tab === "history"} onClick={goHistory} icon={History} label="History" />
          </div>
        </header>

        {tab !== "chat" && (
          <div className="flex flex-wrap items-center gap-2 border-b border-white/[0.04] px-4 py-2.5 sm:gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-600">
              <Building2 className="h-4 w-4 text-white" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-white/90">Financial Analyst</span>
                <Badge variant="outline" className="border-indigo-500/30 px-1.5 py-0 text-[10px] uppercase tracking-wider text-indigo-400">
                  Template
                </Badge>
              </div>
              <p className="break-words text-xs text-white/50">
                {workerName} · {propertyCount} properties · {vendorCount} vendors
              </p>
            </div>

            {tab === "feed" && (
              <div className="flex w-full items-center gap-2 sm:ml-auto sm:w-auto">
                <div className="relative w-full sm:w-[min(26rem,42vw)] sm:max-w-sm" ref={searchRef}>
                  <Search className="pointer-events-none absolute left-3 top-1/2 z-10 h-3.5 w-3.5 -translate-y-1/2 text-white/45" />
                  <input
                    value={search}
                    onFocus={() => setSearchOpen(true)}
                    onChange={(e) => { setSearch(e.target.value); setSearchOpen(true); }}
                    placeholder="Search"
                    className="h-[34px] w-full rounded-lg border border-white/[0.08] bg-white/[0.04] pl-8 pr-3 text-xs text-white/85 outline-none placeholder:text-white/45 focus:border-indigo-400/45"
                  />
                  {searchOpen && search.trim().length > 0 && (
                    <div className="absolute left-0 right-0 top-full z-50 mt-1.5 max-h-72 overflow-y-auto rounded-xl border border-white/[0.08] p-1.5 shadow-2xl" style={{ background: PANEL_BG }}>
                      {suggestions.length > 0 ? suggestions.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => { router.push(s.href); setSearchOpen(false); setSearch(""); }}
                          className="flex w-full flex-col items-start rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-white/[0.06]"
                        >
                          <span className="text-xs font-medium text-white/90">{s.title}</span>
                          <span className="text-[11px] text-white/55">{s.subtitle}</span>
                        </button>
                      )) : (
                        <p className="px-2.5 py-2 text-xs text-white/55">No matches for &quot;{search}&quot; in current response data.</p>
                      )}
                    </div>
                  )}
                </div>

                <div className="relative" ref={dateRef}>
                  <button
                    type="button"
                    onClick={() => setDateOpen((v) => !v)}
                    className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs transition-all hover:border-white/[0.15] hover:bg-white/[0.06]"
                  >
                    <Calendar className="h-3.5 w-3.5 text-indigo-400" />
                    <span className="font-medium text-white/80">{selectedLabel}</span>
                    <ChevronDown className={cn("h-3 w-3 text-white/45 transition-transform", dateOpen && "rotate-180")} />
                  </button>
                  {dateOpen && (
                    <div className="absolute right-0 top-full z-50 mt-1.5 w-56 overflow-hidden rounded-xl border border-white/[0.08] shadow-2xl" style={{ background: PANEL_BG }}>
                      <div className="border-b border-white/[0.06] px-3 py-2">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-white/45">Date Range</span>
                      </div>
                      <div className="max-h-64 overflow-y-auto py-1">
                        <div className="border-t border-white/[0.04] px-3 pb-1 pt-2">
                          <button
                            type="button"
                            onClick={() => { setMonth("all"); setDateOpen(false); }}
                            className={cn("flex w-full items-center justify-between py-1.5 text-xs", month === "all" ? "font-medium text-indigo-300" : "text-white/68 hover:text-white/88")}
                          >
                            All time
                            {month === "all" && <Check className="h-3.5 w-3.5 text-indigo-300" />}
                          </button>
                        </div>
                        {Object.entries(monthsByYear).sort(([a], [b]) => Number(b) - Number(a)).map(([year, options]) => (
                          <div key={year}>
                            <div className="border-t border-white/[0.04] px-3 pb-1 pt-2">
                              <span className="text-[10px] font-semibold uppercase tracking-wider text-white/34">{year}</span>
                            </div>
                            {options.map((opt) => (
                              <button
                                key={opt.value}
                                type="button"
                                onClick={() => { setMonth(opt.value); setDateOpen(false); }}
                                className={cn("flex w-full items-center justify-between px-3 py-2 text-xs",
                                  opt.value === month ? "bg-indigo-500/10 font-medium text-indigo-400" : "text-white/68 hover:bg-white/[0.05] hover:text-white/88")}
                              >
                                {opt.label}
                                {opt.value === month && <Check className="h-3.5 w-3.5 text-indigo-400" />}
                              </button>
                            ))}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  onClick={() => setFilesOpen(true)}
                  className="inline-flex h-[34px] items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 text-xs text-white/82 transition-colors hover:bg-white/[0.06]"
                >
                  <Upload className="h-3.5 w-3.5 text-cyan-300" /> Files
                </button>
                <button
                  type="button"
                  onClick={() => setMobileTrendsOpen(true)}
                  className="inline-flex h-[34px] items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 text-xs text-white/82 transition-colors hover:bg-white/[0.06] xl:hidden"
                >
                  <MessageSquare className="h-3.5 w-3.5 text-indigo-300" /> Trends
                </button>
              </div>
            )}
          </div>
        )}

        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* EL-1016/EL-1019: this used to be a `tab === "chat" ? X : Y` ternary, which fully
              unmounted whichever side wasn't active. That destroyed FinanceChatPanel's in-memory
              messages every time you left the Chat tab (looked like the chat "clearing all the
              data"), and dropped scroll position/local state on the dashboard side too (felt like
              "the page refreshes"). Keep both sides mounted always and hide the inactive one with
              CSS instead. */}
          <div className={cn("min-h-0 w-full min-w-0 flex-1 overflow-hidden p-4", tab === "chat" ? "flex" : "hidden")}>
            <FinanceChatPanel
              agentId={agentId}
              workerName={workerName}
              pendingPrompt={pendingPrompt}
              onPendingConsumed={() => setPendingPrompt(null)}
            />
          </div>
          <div className={cn("flex min-h-0 min-w-0 flex-1 overflow-hidden", tab === "chat" && "hidden")}>
            <main className="flex min-h-0 min-w-0 w-full flex-1 flex-col overflow-hidden">
              {children}
            </main>
            {tab === "feed" && isDashboard && (
              <aside className="order-3 hidden w-[340px] shrink-0 flex-col border-l border-white/[0.06] xl:flex">
                <div className="h-full p-4 xl:p-5">
                  <section className="flex h-full flex-col overflow-hidden rounded-2xl border border-white/[0.08]" style={{ background: "oklch(0.16 0.02 250)" }}>
                    <InsightRail
                      sections={sections}
                      onInsightClick={(text, section, title) => {
                        setPendingPrompt(title ? `${title}: ${text}` : `${section}: ${text}`);
                        setChatTab(true);
                      }}
                    />
                  </section>
                </div>
              </aside>
            )}
          </div>
        </div>

        {mobileTrendsOpen && tab === "feed" && isDashboard && (
          <div className="fixed inset-0 z-50 xl:hidden" style={{ background: "oklch(0.15 0.025 250)" }}>
            <div className="flex h-14 items-center justify-between border-b border-white/[0.06] px-4">
              <p className="text-sm text-white/90">Trends</p>
              <button type="button" className="text-xs text-white/60" onClick={() => setMobileTrendsOpen(false)}>Close</button>
            </div>
            <InsightRail
              sections={sections}
              className="h-[calc(100%-56px)]"
              onInsightClick={(text, section, title) => {
                setMobileTrendsOpen(false);
                setPendingPrompt(title ? `${title}: ${text}` : `${section}: ${text}`);
                setChatTab(true);
              }}
            />
          </div>
        )}

        <FinanceFileManagerDialog agentId={agentId} open={filesOpen} onOpenChange={setFilesOpen} onUploaded={() => setMonth("all")} />
      </div>
    </AppShell>
  );
}

function TabButton({ active, onClick, icon: Icon, label }: { active: boolean; onClick: () => void; icon: React.ElementType; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50",
        active ? "bg-white/[0.12] text-white" : "text-white/50 hover:text-white/75",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}
