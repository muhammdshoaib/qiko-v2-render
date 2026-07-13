"use client";

import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, Boxes } from "lucide-react";
import { listAgents, listSalesOpportunities, type SalesOpportunity } from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OutcomesStrip } from "@/components/sales-intelligence/outcomes-strip";
import { formatCompact, formatDate, stageBadgeClass, STAGE_LABELS } from "@/components/sales-intelligence/utils";

export default function SalesIntelligenceOverviewPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const oppsQ = useQuery({
    queryKey: ["sales-opportunities", agentId],
    queryFn: () => listSalesOpportunities(agentId),
    retry: false,
  });
  const opps: SalesOpportunity[] = oppsQ.data?.opportunities ?? [];

  const metrics = useMemo(() => {
    const newFound = opps.filter((o) => o.stage === "ingested").length;
    const qualified = opps.filter((o) => ["qualified", "validated", "ready_salesforce", "push_pending", "pushed"].includes(o.stage)).length;
    const awaitingReview = opps.filter((o) => o.stage === "awaiting_review").length;
    const rejected = opps.filter((o) => ["rejected", "push_failed"].includes(o.stage)).length;
    const pipelineValue = opps
      .filter((o) => !["rejected", "push_failed"].includes(o.stage))
      .reduce((sum, o) => sum + (o.estimatedValue ?? 0), 0);
    return { newFound, qualified, awaitingReview, rejected, pipelineValue };
  }, [opps]);

  const statusBuckets = useMemo(() => {
    const buckets = { "Early Pipeline": 0, "Needs Review": 0, "Ready for SF": 0, Rejected: 0 };
    for (const o of opps) {
      if (["ingested", "qualifying", "qualified"].includes(o.stage)) buckets["Early Pipeline"]++;
      else if (o.stage === "awaiting_review") buckets["Needs Review"]++;
      else if (["validated", "ready_salesforce", "push_pending", "pushed"].includes(o.stage)) buckets["Ready for SF"]++;
      else if (["rejected", "push_failed"].includes(o.stage)) buckets.Rejected++;
    }
    return Object.entries(buckets).map(([name, value]) => ({ name, value }));
  }, [opps]);

  const qualificationRate = useMemo(() => {
    const validated = opps.filter((o) => ["validated", "ready_salesforce", "push_pending", "pushed"].includes(o.stage)).length;
    const rejected = opps.filter((o) => o.stage === "rejected").length;
    const total = validated + rejected;
    const pct = total > 0 ? Math.round((validated / total) * 100) : 0;
    return { pct, validated, rejected, total };
  }, [opps]);

  const bySource = useMemo(() => {
    const map = new Map<string, number>();
    for (const o of opps) map.set((o.sourceKey || "unknown").toUpperCase(), (map.get((o.sourceKey || "unknown").toUpperCase()) ?? 0) + 1);
    return Array.from(map.entries()).map(([name, value]) => ({ name, value }));
  }, [opps]);

  const lastScan = opps.map((o) => o.createdAt).filter(Boolean).sort().slice(-1)[0];
  const recent = [...opps].sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || "")).slice(0, 5);

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="overview">
      <div className="space-y-6">
        <OutcomesStrip title="OVERVIEW" tiles={[
          { value: String(metrics.newFound), label: "New Opportunities Found", caption: "since last portal scan", trend: "up" },
          { value: String(metrics.qualified), label: "Qualified Opportunities", caption: "AI + human validated", trend: "up" },
          { value: String(metrics.awaitingReview), label: "Awaiting Review", caption: "human validation queue", trend: metrics.awaitingReview > 0 ? "down" : "neutral" },
          { value: String(metrics.rejected), label: "Rejected", caption: "no bid / declined", trend: metrics.rejected > 0 ? "down" : "neutral" },
          { value: formatCompact(metrics.pipelineValue), label: "Pipeline Value Identified", caption: "active opportunities", trend: "up" },
        ]} />

        <div className="flex items-start gap-4 rounded-2xl border border-white/[0.06] bg-white/[0.015] p-6">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400">
            <Boxes className="size-5" />
          </span>
          <div>
            <h2 className="text-[15px] font-semibold text-white">Opportunity intelligence</h2>
            <p className="mt-1 text-[13px] text-slate-400">
              Track ingested tenders, qualification status, human review queue, and Salesforce push readiness across all sources.
            </p>
            <p className="mt-2 flex items-center gap-1.5 text-[12px] text-slate-500">
              <span className="size-1.5 rounded-full bg-emerald-400" /> Last portal scan: {formatDate(lastScan)}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <ChartCard title="Pipeline by Status" subtitle={`${opps.length} of ${opps.length} opportunities mapped to stages`}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={statusBuckets} layout="vertical" margin={{ left: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
                <XAxis type="number" stroke="#64748b" fontSize={11} allowDecimals={false} />
                <YAxis type="category" dataKey="name" stroke="#64748b" fontSize={11} width={90} />
                <Tooltip contentStyle={{ background: "#0f1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="value" fill="#818cf8" radius={[0, 4, 4, 0]} barSize={18} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Qualification Rate" subtitle={`${qualificationRate.pct}% validated of reviewed outcomes`}>
            <div className="relative flex h-[220px] items-center justify-center">
              <ResponsiveContainer width={180} height={180}>
                <PieChart>
                  <Pie data={[{ name: "Validated", value: qualificationRate.validated || 1 }, { name: "Rejected", value: qualificationRate.rejected }]}
                    dataKey="value" innerRadius={64} outerRadius={82} startAngle={90} endAngle={-270} stroke="none">
                    <Cell fill="#818cf8" />
                    <Cell fill="#f87171" />
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute flex flex-col items-center">
                <span className="text-3xl font-bold text-white">{qualificationRate.pct}%</span>
                <span className="text-[11px] text-slate-500">validated</span>
              </div>
            </div>
            <div className="mt-1 flex items-center justify-center gap-4 text-[11px] text-slate-400">
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-[#818cf8]" /> Validated</span>
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-[#f87171]" /> Rejected</span>
            </div>
          </ChartCard>

          <ChartCard title="Opportunities by Source" subtitle={`${opps.length} ingested across ${bySource.length} sources`}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={bySource}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "#0f1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={36}>
                  {bySource.map((_, i) => <Cell key={i} fill={i === 0 ? "#818cf8" : "#c084fc"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-[15px] font-semibold text-white">Recent Opportunities</h2>
              <p className="mt-0.5 text-[12px] text-slate-500">Latest activity across your pipeline</p>
            </div>
            <span className="flex size-6 items-center justify-center rounded-full bg-white/[0.05] text-[11px] font-semibold text-slate-300">
              {recent.length}
            </span>
          </div>
          {oppsQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {!oppsQ.isLoading && recent.length === 0 && <p className="text-sm text-slate-500">No opportunities ingested yet.</p>}
          <div className="divide-y divide-white/[0.05]">
            {recent.map((o) => (
              <button key={o.id} onClick={() => router.push(`/studio/${agentId}/sales-intelligence/pipeline/${o.id}`)}
                className="flex w-full items-center justify-between gap-3 py-3 text-left hover:bg-white/[0.02]">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-white">{o.title}</p>
                  <p className="mt-0.5 truncate text-[12px] text-slate-500">{o.buyer || o.source}</p>
                </div>
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${stageBadgeClass(o.stage)}`}>
                  {STAGE_LABELS[o.stage] ?? o.stage}
                </span>
                <ArrowRight className="size-4 shrink-0 text-slate-600" />
              </button>
            ))}
          </div>
        </div>
      </div>
    </CockpitShell>
  );
}

function ChartCard({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <h3 className="text-[14px] font-semibold text-white">{title}</h3>
      <p className="mt-0.5 text-[11px] text-slate-500">{subtitle}</p>
      <div className="mt-3">{children}</div>
    </div>
  );
}
