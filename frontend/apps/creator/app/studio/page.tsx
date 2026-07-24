"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowRight, BarChart3, FileText, MessageSquare, Plus, Radar } from "lucide-react";
import { Button } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  getFinanceAnalytics, listAgents, listDocuments, listRfpPacks, listSalesOpportunities,
  type Agent, type FinanceAnalytics, type RfpPack, type SalesOpportunity,
} from "@/lib/api";
import { normalizeFinanceSummary } from "@/components/finance/utils";
import {
  AI_DRAFTING_DESCRIPTION,
  aiDraftingPercent,
  knowledgeChunkCount,
  nextBidDeadline,
} from "@/components/pre-sales/metrics";
import { MetricInfoTooltip } from "@/components/pre-sales/metric-info-tooltip";
import { formatShortDate, toTitleFromSlug } from "@/lib/stringUtils";

function workerCategory(a: Agent): string {
  const expertise = a.config?.expertise as string | undefined;
  return expertise?.trim() || "General";
}

// The Sales Intelligence worker (IdgSalesController's opportunity pipeline) has its own cockpit
// under /studio/[id]/sales-intelligence instead of the generic RFP-pack tab layout -- identified
// by atype, same field the Creator side uses to pick a worker's build wizard.
function isSalesIntelligenceWorker(a: Agent): boolean {
  return a.atype === "sales_intelligence";
}

// The Financial Analyst worker has its own analytics dashboard under /studio/[id]/finance.
function isFinanceWorker(a: Agent): boolean {
  return a.atype === "finance";
}

function formatCompactCurrency(value: number, currency = "GBP"): string {
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }).format(value);
  } catch {
    return `£${(value / 1000000).toFixed(1)}M`;
  }
}

export default function StudioPage() {
  const router = useRouter();
  const agentsQ = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const workers = agentsQ.data ?? [];

  // "Deployed" here means live/ready -- Creator is where workers are built and trained,
  // Studio is where the deployed ones are operated day to day.
  const deployed = useMemo(() => workers.filter((a) => a.status === "ready"), [workers]);

  const packsQ = useQueries({
    queries: deployed.map((a) => ({
      queryKey: ["rfp-packs", a.id],
      queryFn: () => listRfpPacks(a.id),
      enabled: a.atype === "pre_sales_writer",
      retry: false,
    })),
  });
  const opportunitiesQ = useQueries({
    queries: deployed.map((a) => ({
      queryKey: ["sales-opportunities", a.id],
      queryFn: () => listSalesOpportunities(a.id),
      enabled: isSalesIntelligenceWorker(a),
      retry: false,
    })),
  });
  const financeQ = useQueries({
    queries: deployed.map((a) => ({
      queryKey: ["finance-analytics", a.id, "all"],
      queryFn: () => getFinanceAnalytics(a.id),
      enabled: isFinanceWorker(a),
      retry: false,
    })),
  });
  const docsQ = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const dataVolume = knowledgeChunkCount(docsQ.data ?? []);

  const groups = useMemo(() => {
    const byCategory = new Map<string, Agent[]>();
    for (const a of deployed) {
      const key = workerCategory(a);
      byCategory.set(key, [...(byCategory.get(key) ?? []), a]);
    }
    return Array.from(byCategory.entries());
  }, [deployed]);

  return (
    <AppShell title="Studio">
      <div className="flex min-h-screen flex-col bg-[#050810]">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-10 lg:px-12">
          <div className="mb-8 flex flex-col gap-4 sm:mb-10 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-bold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>Studio</h1>
              <p className="mt-1 text-[13px] text-slate-500">Your deployed workers, ready to manage and use</p>
            </div>
            <button onClick={() => router.push("/workers")}
              className="flex items-center gap-2 rounded-xl bg-indigo-500 px-4 py-2.5 text-[13px] font-semibold text-white shadow-lg shadow-indigo-500/15 transition-all hover:bg-indigo-400">
              <Plus className="size-4" /> Deploy Worker
            </button>
          </div>

          {agentsQ.isLoading && <p className="text-sm text-slate-400">Loading…</p>}

          {!agentsQ.isLoading && deployed.length === 0 && (
            <div className="py-16 text-center">
              <p className="mb-3 text-sm text-slate-400">No deployed workers yet - mark a worker ready in Creator first.</p>
              <Button variant="outline" onClick={() => router.push("/workers")}>Go to Workers</Button>
            </div>
          )}

          <div className="space-y-10">
            {groups.map(([category, items]) => (
              <section key={category}>
                <div className="mb-5">
                  <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{category}</h2>
                  <p className="mt-1 text-[12px] text-slate-500">Deployed and managed from here</p>
                </div>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  {items.map((a) => {
                    const idx = deployed.findIndex((d) => d.id === a.id);
                    const salesIntel = isSalesIntelligenceWorker(a);
                    const finance = isFinanceWorker(a);
                    const preSales = a.atype === "pre_sales_writer";

                    let metrics: { label: string; value: string; description?: string }[];
                    let useCaseCount: number;
                    let href: string;
                    if (finance) {
                      const analytics: FinanceAnalytics | undefined = financeQ[idx]?.data;
                      const s = normalizeFinanceSummary(analytics?.summary);
                      const props = (analytics?.properties ?? []).filter((p) => (p.income ?? 0) || (p.expenses ?? 0));
                      const propertyCount = s.propertyCount || props.length;
                      const riskProps = props.filter((p) => Number(p.riskScore ?? 0) > 0);
                      const avgRisk = riskProps.length
                        ? Math.round(riskProps.reduce((sum, p) => sum + Number(p.riskScore ?? 0), 0) / riskProps.length)
                        : 0;
                      metrics = [
                        { label: "Properties", value: propertyCount > 0 ? String(propertyCount) : "-" },
                        { label: "Total Income", value: s.totalIncome > 0 ? formatCompactCurrency(s.totalIncome) : "-" },
                        { label: "Net Profit", value: s.netProfit ? formatCompactCurrency(s.netProfit) : "-" },
                        { label: "Avg Risk", value: avgRisk > 0 ? `${avgRisk}/100` : "-" },
                      ];
                      useCaseCount = 3;
                      href = `/studio/${a.id}/finance`;
                    } else if (salesIntel) {
                      const opps: SalesOpportunity[] = opportunitiesQ[idx]?.data?.opportunities ?? [];
                      const newFound = opps.filter((o) => o.stage === "ingested").length;
                      const qualified = opps.filter((o) => o.stage === "qualified" || o.stage === "validated").length;
                      const awaitingReview = opps.filter((o) => o.stage === "awaiting_review").length;
                      const pipelineValue = opps
                        .filter((o) => !["rejected", "push_failed"].includes(o.stage))
                        .reduce((sum, o) => sum + (o.estimatedValue ?? 0), 0);
                      metrics = [
                        { label: "New Found", value: String(newFound) },
                        { label: "Qualified", value: String(qualified) },
                        { label: "Awaiting Review", value: String(awaitingReview) },
                        { label: "Pipeline Value", value: pipelineValue > 0 ? formatCompactCurrency(pipelineValue) : "-" },
                      ];
                      useCaseCount = 5;
                      href = `/studio/${a.id}/sales-intelligence`;
                    } else if (preSales) {
                      const packs: RfpPack[] = packsQ[idx]?.data ?? [];
                      const activeBids = packs.length;
                      const aiDrafting = aiDraftingPercent(packs);
                      metrics = [
                        { label: "Active Bids", value: String(activeBids) },
                        {
                          label: "AI Drafting",
                          value: aiDrafting === null ? "-" : `${aiDrafting}%`,
                          description: AI_DRAFTING_DESCRIPTION,
                        },
                        { label: "Data Volume", value: `${dataVolume} chunks` },
                        { label: "Next Bid", value: formatShortDate(nextBidDeadline(packs, Date.now())) },
                      ];
                      useCaseCount = 6;
                      href = `/studio/${a.id}/pre-sales`;
                    } else {
                      // Generic worker boilerplate: domain-neutral knowledge/grounding metrics.
                      metrics = [
                        { label: "Status", value: a.status === "ready" ? "Ready" : "Training" },
                        { label: "Knowledge", value: `${dataVolume} chunks` },
                        { label: "Grounding", value: "Critic + gate" },
                        { label: "Channels", value: "Chat · Voice" },
                      ];
                      useCaseCount = 4;
                      href = `/studio/${a.id}`;
                    }

                    return (
                      <div
                        key={a.id}
                        role="link"
                        tabIndex={0}
                        onClick={() => router.push(href)}
                        onKeyDown={(event) => {
                          if (event.target !== event.currentTarget) return;
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            router.push(href);
                          }
                        }}
                        className="group w-full cursor-pointer overflow-hidden rounded-2xl border border-white/[0.06] text-left transition-all duration-300 hover:border-indigo-500/30 hover:shadow-[0_0_60px_-15px_rgba(99,102,241,0.12)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
                        style={{ background: "linear-gradient(165deg, rgba(255,255,255,0.024) 0%, rgba(255,255,255,0.004) 100%)" }}
                      >
                        <div className="px-6 pt-6 pb-4">
                          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div className="flex items-center gap-3.5">
                              {finance ? (
                                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.18)" }}>
                                  <BarChart3 className="size-5 text-emerald-400" />
                                </span>
                              ) : salesIntel ? (
                                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(34,211,238,0.08)", border: "1px solid rgba(34,211,238,0.18)" }}>
                                  <Radar className="size-5 text-cyan-400" />
                                </span>
                              ) : preSales ? (
                                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(168,85,247,0.08)", border: "1px solid rgba(168,85,247,0.18)" }}>
                                  <FileText className="size-5 text-purple-400" />
                                </span>
                              ) : (
                                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.15)" }}>
                                  <MessageSquare className="size-5 text-indigo-400" />
                                </span>
                              )}
                              <div>
                                <h3 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{a.name}</h3>
                                <p className="mt-0.5 text-[11px] text-slate-500">{toTitleFromSlug(a.atype) || category}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 self-start sm:self-auto">
                              <span className="flex items-center gap-1.5 rounded-full bg-emerald-400/[0.08] px-2.5 py-[3px] text-[9px] font-semibold uppercase tracking-wider text-emerald-400/80">
                                <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" /> Active
                              </span>
                              <ArrowRight className="size-4 text-slate-700 transition-colors group-hover:text-slate-400" />
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
                            {metrics.map((m) => (
                              <div
                                key={m.label}
                                className="rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-2.5"
                              >
                                <p className="text-[17px] font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>{m.value}</p>
                                <p className="mt-0.5 flex items-center gap-0.5 text-[9px] text-slate-500">
                                  <span>{m.label}</span>
                                  {m.description && (
                                    <MetricInfoTooltip label={m.label} description={m.description} />
                                  )}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center justify-between border-t border-white/[0.05] px-6 py-3 text-[11px] text-slate-500">
                          <span>{useCaseCount} active use cases</span>
                          <span className="flex items-center gap-1 text-slate-400 transition-colors group-hover:text-indigo-400">
                            Open <ArrowRight className="size-3" />
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
