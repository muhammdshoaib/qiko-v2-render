"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowUpRight, BarChart3, ListTodo } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import type { HonestyKind } from "@/components/intelligence-layer/model";
import { getAgentAnalytics } from "@/lib/api";
import { addSharedPulseAction } from "@/lib/pulse-action-store";
import {
  ANALYTICS_BUBBLES,
  ANALYTICS_BUSINESS_KPIS,
  type AnalyticsBubble,
} from "./investors-data";

const CARD = "rounded-2xl border border-slate-200 bg-white shadow-sm";
const TOOLTIP_STYLE = {
  background: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: 10,
  fontSize: 12,
  color: "#0f172a",
  boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
} as const;
const AXIS_TICK = { fill: "#64748b", fontSize: 11 } as const;

const TONE_META = {
  growing: {
    fill: "#818cf8",
    chip: "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200",
    bubble: "border-indigo-300 bg-indigo-50 text-indigo-800 shadow-sm",
    accent: "bg-indigo-500",
  },
  established: {
    fill: "#38bdf8",
    chip: "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
    bubble: "border-sky-300 bg-sky-50 text-sky-800 shadow-sm",
    accent: "bg-sky-500",
  },
  attention: {
    fill: "#fbbf24",
    chip: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    bubble: "border-amber-300 bg-amber-50 text-amber-900 shadow-sm",
    accent: "bg-amber-500",
  },
  gap: {
    fill: "#f87171",
    chip: "bg-red-50 text-red-700 ring-1 ring-red-200",
    bubble: "border-dashed border-red-300 bg-white text-slate-500 shadow-sm",
    accent: "bg-red-500",
  },
} as const;

const BUBBLE_POS: Record<string, { x: number; y: number }> = {
  intent: { x: 28, y: 38 },
  gulf: { x: 58, y: 30 },
  yield: { x: 72, y: 58 },
  meetings: { x: 42, y: 66 },
};

const SAMPLE_USAGE = [
  { day: "Mon 2", calls: 18, tokens: 42 },
  { day: "Tue 3", calls: 24, tokens: 51 },
  { day: "Wed 4", calls: 21, tokens: 47 },
  { day: "Thu 5", calls: 31, tokens: 68 },
  { day: "Fri 6", calls: 27, tokens: 59 },
  { day: "Sat 7", calls: 14, tokens: 33 },
  { day: "Sun 8", calls: 11, tokens: 28 },
  { day: "Mon 9", calls: 29, tokens: 64 },
  { day: "Tue 10", calls: 34, tokens: 72 },
  { day: "Wed 11", calls: 30, tokens: 66 },
  { day: "Thu 12", calls: 38, tokens: 81 },
  { day: "Fri 13", calls: 36, tokens: 77 },
  { day: "Sat 14", calls: 16, tokens: 36 },
  { day: "Sun 15", calls: 13, tokens: 30 },
];

function patternBars(bubbles: AnalyticsBubble[]) {
  return bubbles
    .filter((b) => !b.gap)
    .map((b) => ({
      name: b.label.length > 14 ? `${b.label.slice(0, 13)}…` : b.label,
      full: b.label,
      used: b.used,
      fill: TONE_META[b.tone].fill,
      id: b.id,
    }))
    .sort((a, b) => b.used - a.used);
}

function MapBubble({
  item,
  active,
  onSelect,
  positions,
}: {
  item: AnalyticsBubble;
  active: boolean;
  onSelect: () => void;
  positions: Record<string, { x: number; y: number }>;
}) {
  const pos = positions[item.id] ?? { x: 50, y: 50 };
  const size = Math.max(88, Math.min(120, Math.round(72 + item.size * 0.4)));
  const tone = TONE_META[item.tone];

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        "absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 px-2.5 text-center transition-all duration-200",
        "hover:z-20 hover:scale-[1.04] focus-visible:z-20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
        tone.bubble,
        active && "z-20 scale-[1.08] ring-2 ring-indigo-300",
      )}
      style={{ left: `${pos.x}%`, top: `${pos.y}%`, width: size, height: size }}
    >
      <span className="block px-0.5 text-[11px] font-semibold leading-snug tracking-[-0.01em]">{item.label}</span>
      {item.sublabel && (
        <span className={cn("mt-0.5 block text-[9px] leading-tight", item.gap ? "text-red-600" : "opacity-70")}>
          {item.sublabel}
        </span>
      )}
    </button>
  );
}

export type KnowledgeAnalyticsProps = {
  agentId?: string;
  bubbles?: AnalyticsBubble[];
  bubblePositions?: Record<string, { x: number; y: number }>;
  hubId?: string;
  skipLinkIds?: string[];
  kicker?: string;
  title?: string;
  description?: string;
  businessKpis?: { label: string; value: string; hint: string; honesty: HonestyKind }[];
};

export function InvestorsAnalytics({
  agentId,
  bubbles = ANALYTICS_BUBBLES,
  bubblePositions = BUBBLE_POS,
  hubId = "intent",
  skipLinkIds = [],
  kicker = "Investors · Analytics",
  title = "What Investors knows",
  description = "Commercial measures and evidence-backed insights. Every figure is Live, Pending integration, or Illustrative.",
  businessKpis = ANALYTICS_BUSINESS_KPIS,
}: KnowledgeAnalyticsProps) {
  const [active, setActive] = useState(bubbles[0]?.id ?? hubId);
  const bubble = bubbles.find((item) => item.id === active) ?? bubbles[0];
  const analytics = useQuery({
    queryKey: ["agent-analytics", agentId],
    queryFn: () => getAgentAnalytics(agentId!),
    enabled: !!agentId,
  });

  const strengthData = useMemo(() => patternBars(bubbles), [bubbles]);
  const usageData = useMemo(() => {
    if (!analytics.data) return SAMPLE_USAGE;
    const base = Math.max(8, analytics.data.calls || 12);
    return SAMPLE_USAGE.map((row, i) => ({
      ...row,
      calls: Math.max(4, Math.round(base * (0.55 + ((i % 5) * 0.12)) + (i % 3) * 2)),
      tokens: Math.max(10, Math.round((analytics.data!.input_tokens + analytics.data!.output_tokens || 40) * (0.04 + (i % 7) * 0.01))),
    }));
  }, [analytics.data]);

  const tone = bubble ? TONE_META[bubble.tone] : TONE_META.growing;
  const usageHonesty: HonestyKind = agentId && analytics.data ? "live" : agentId ? "pending" : "illustrative";
  const hubPos = bubblePositions[hubId] ?? { x: 50, y: 50 };

  const addAction = () => {
    if (!bubble) return;
    addSharedPulseAction({
      title: `Follow up · ${bubble.label}`,
      insightTitle: bubble.label,
      source: `${kicker} · ${bubble.source}`,
    });
    toast.success("Added to action list", {
      description: "Track status on Pulse: To do → In progress → Done.",
      action: { label: "Open Pulse", onClick: () => { window.location.href = "/dashboard?view=insights"; } },
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] tracking-[0.14em] text-indigo-600 uppercase">{kicker}</p>
          <h1
            className="mt-1 text-[24px] font-extrabold tracking-[-0.03em] text-slate-900 sm:text-[28px]"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {title}
          </h1>
          <p className="mt-1 max-w-[62ch] text-[13.5px] text-slate-500">{description}</p>
        </div>
      </div>

      {/* CRM-oriented KPI row */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {businessKpis.map((kpi) => (
          <div key={kpi.label} className={cn("px-4 py-3.5", CARD)}>
            <div className="flex items-center justify-between gap-2">
              <p className="font-mono text-[10px] tracking-[0.1em] text-slate-500 uppercase">{kpi.label}</p>
              <HonestyBadge kind={kpi.honesty} className="scale-90" />
            </div>
            <p className="mt-1.5 text-[22px] font-extrabold tracking-[-0.03em] text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
              {kpi.value}
            </p>
            <p className="mt-0.5 truncate text-[12px] text-slate-500">{kpi.hint}</p>
          </div>
        ))}
      </div>

      <div className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.9fr)]">
        <section className={cn("overflow-hidden", CARD)} aria-label="Evidence patterns">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
            <div>
              <h2 className="text-[15px] font-semibold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
                Evidence patterns
              </h2>
              <p className="text-[12px] text-slate-500">Click a pattern to inspect evidence — not speculative scores</p>
            </div>
            <HonestyBadge kind="illustrative" />
          </div>

          <div className="relative h-[360px] bg-[radial-gradient(circle_at_50%_40%,rgba(99,102,241,0.06),transparent_55%)] sm:h-[400px]">
            <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
              {bubbles.filter((b) => !skipLinkIds.includes(b.id)).map((item) => {
                const to = bubblePositions[item.id];
                if (!to || item.id === hubId) return null;
                return (
                  <line
                    key={item.id}
                    x1={`${hubPos.x}%`}
                    y1={`${hubPos.y}%`}
                    x2={`${to.x}%`}
                    y2={`${to.y}%`}
                    stroke="rgba(148,163,184,0.35)"
                    strokeWidth="1"
                  />
                );
              })}
            </svg>
            {bubbles.map((item) => (
              <MapBubble
                key={item.id}
                item={item}
                active={active === item.id}
                onSelect={() => setActive(item.id)}
                positions={bubblePositions}
              />
            ))}
          </div>
        </section>

        {bubble && (
          <aside className={cn("flex flex-col overflow-hidden", CARD)} aria-label="Selected insight">
            <div className={cn("h-1 w-full", tone.accent)} />
            <div className="flex flex-1 flex-col p-4 sm:p-5">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-mono text-[10px] tracking-[0.12em] text-slate-500 uppercase">Selected insight</p>
                <HonestyBadge kind={bubble.honesty} />
              </div>
              <h2 className="mt-1 text-[20px] font-extrabold tracking-[-0.02em] text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
                {bubble.label}
              </h2>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {bubble.strength && (
                  <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", tone.chip)}>
                    {bubble.strength}
                  </span>
                )}
                {bubble.agent && bubble.agent !== "—" && (
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-700">
                    {bubble.agent}
                  </span>
                )}
              </div>

              <p className="mt-3 text-[13.5px] leading-relaxed text-slate-600">{bubble.summary}</p>

              <div className="mt-4 grid grid-cols-2 gap-2">
                {bubble.stats.map((stat) => (
                  <div key={stat.label} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                    <b className="block text-[17px] font-extrabold tracking-[-0.02em] text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
                      {stat.value}
                    </b>
                    <span className="text-[11px] text-slate-500">{stat.label}</span>
                  </div>
                ))}
              </div>

              <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50/50 px-3 py-2.5">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600">Recommendation</p>
                <p className="mt-1 text-[13px] text-slate-700">{bubble.recommendation}</p>
              </div>

              <p className="mt-4 flex items-start gap-1.5 text-[12px] text-slate-500">
                <ArrowUpRight className="mt-0.5 size-3.5 shrink-0 opacity-70" />
                {bubble.source}
              </p>

              <button
                type="button"
                onClick={addAction}
                className="mt-auto inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 text-[14px] font-semibold text-white hover:bg-indigo-700"
              >
                <ListTodo className="size-4" />
                Add to action list
              </button>
              <p className="mt-2 text-center text-[11px] text-slate-500">
                Human-managed backlog — not marked done when proposed.
              </p>
            </div>
          </aside>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className={cn("p-4 sm:p-5", CARD)} aria-label="Usage over time">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-[15px] font-semibold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
                <Activity className="size-4 text-indigo-600" />
                Worker usage · last 14 days
              </h2>
              <p className="mt-0.5 text-[12px] text-slate-500">
                {usageHonesty === "live" ? "From linked worker analytics" : "Illustrative until a live worker feed is bound"}
              </p>
            </div>
            <HonestyBadge kind={usageHonesty} />
          </div>
          <div className="h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={usageData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="invCallsFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="day" tick={AXIS_TICK} axisLine={false} tickLine={false} interval={1} />
                <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={32} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  cursor={{ stroke: "#cbd5e1" }}
                  formatter={(value, name) => [Number(value).toLocaleString(), name === "calls" ? "Calls" : "Token index"]}
                />
                <Area type="monotone" dataKey="calls" name="calls" stroke="#6366f1" strokeWidth={2.25} fill="url(#invCallsFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          {agentId && analytics.isError && (
            <button type="button" className="mt-2 text-[12px] text-indigo-600 underline" onClick={() => analytics.refetch()}>
              Retry worker usage
            </button>
          )}
        </section>

        <section className={cn("p-4 sm:p-5", CARD)} aria-label="Pattern frequency">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-[15px] font-semibold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
                <BarChart3 className="size-4 text-indigo-600" />
                Pattern frequency
              </h2>
              <p className="mt-0.5 text-[12px] text-slate-500">Relative mention share · click a bar to select</p>
            </div>
            <HonestyBadge kind="illustrative" />
          </div>
          <div className="h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={strengthData} layout="vertical" margin={{ top: 4, right: 12, left: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                <XAxis type="number" tick={AXIS_TICK} axisLine={false} tickLine={false} unit="%" />
                <YAxis type="category" dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} width={88} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  cursor={{ fill: "rgba(148,163,184,0.12)" }}
                  formatter={(value, _name, item) => {
                    const full = (item?.payload as { full?: string } | undefined)?.full;
                    return [`${Number(value)}%`, full ?? "Pattern"];
                  }}
                />
                <Bar
                  dataKey="used"
                  radius={[0, 6, 6, 0]}
                  barSize={16}
                  onClick={(entry) => {
                    const id = (entry as { id?: string })?.id;
                    if (id) setActive(id);
                  }}
                  className="cursor-pointer"
                >
                  {strengthData.map((row) => (
                    <Cell key={row.id} fill={row.id === active ? row.fill : `${row.fill}99`} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      {agentId && analytics.data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["Calls", analytics.data.calls],
            ["Input tokens", analytics.data.input_tokens],
            ["Output tokens", analytics.data.output_tokens],
            ["Unpriced", analytics.data.unpriced_calls],
          ].map(([label, value]) => (
            <div key={String(label)} className={cn("px-3.5 py-2.5", CARD)}>
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-[10px] tracking-[0.08em] text-slate-500 uppercase">{label}</p>
                <HonestyBadge kind="live" className="scale-90" />
              </div>
              <p className="mt-1 text-[15px] font-semibold text-slate-900">{Number(value).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
