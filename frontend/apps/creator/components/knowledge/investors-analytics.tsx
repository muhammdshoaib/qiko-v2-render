"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Sparkles } from "lucide-react";
import {
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
  ANALYTICS_CONVERSATIONS_30D,
  ANALYTICS_CRM_WEEKS,
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

const CLAUDE_SIMULATE_URL = "https://claude.ai/artifact/SfhNos5EWvZ5HkDP6oVp4d";

const TONE_META = {
  growing: {
    fill: "#10b981",
    soft: "rgba(16,185,129,0.14)",
    chip: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    bubble: "border-emerald-400/80 bg-emerald-50 text-emerald-900",
    ring: "ring-emerald-400/50",
    glow: "0 0 0 6px rgba(16,185,129,0.12), 0 10px 28px rgba(16,185,129,0.18)",
    legend: "bg-emerald-500",
  },
  established: {
    fill: "#3b82f6",
    soft: "rgba(59,130,246,0.12)",
    chip: "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
    bubble: "border-sky-400/80 bg-sky-50 text-sky-900",
    ring: "ring-sky-400/50",
    glow: "0 0 0 6px rgba(59,130,246,0.10), 0 10px 28px rgba(59,130,246,0.16)",
    legend: "bg-sky-500",
  },
  attention: {
    fill: "#f59e0b",
    soft: "rgba(245,158,11,0.14)",
    chip: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
    bubble: "border-amber-400/80 bg-amber-50 text-amber-950",
    ring: "ring-amber-400/50",
    glow: "0 0 0 6px rgba(245,158,11,0.12), 0 10px 28px rgba(245,158,11,0.16)",
    legend: "bg-amber-400",
  },
  gap: {
    fill: "#f87171",
    soft: "rgba(248,113,113,0.08)",
    chip: "bg-red-50 text-red-700 ring-1 ring-red-200",
    bubble: "border-dashed border-red-400 bg-white text-red-600",
    ring: "ring-red-300/60",
    glow: "0 0 0 6px rgba(248,113,113,0.08)",
    legend: "border border-dashed border-red-400 bg-transparent",
  },
} as const;

const LEGEND: { tone: keyof typeof TONE_META; label: string }[] = [
  { tone: "growing", label: "Growing" },
  { tone: "established", label: "Established" },
  { tone: "attention", label: "Needs attention" },
  { tone: "gap", label: "Gap (not covered yet)" },
];

/** Radial layout — largest pattern near centre. */
const BUBBLE_POS: Record<string, { x: number; y: number }> = {
  referrals: { x: 46, y: 48 },
  gulf: { x: 22, y: 30 },
  yield: { x: 70, y: 26 },
  service: { x: 78, y: 56 },
  ready: { x: 28, y: 72 },
  offplan: { x: 58, y: 78 },
  selling: { x: 16, y: 54 },
};

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
  const size = Math.max(72, Math.min(128, Math.round(56 + item.size * 0.55)));
  const tone = TONE_META[item.tone];
  const labelBelow = item.gap || item.label.length > 14 || size < 96;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        "absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 text-center transition-all duration-200",
        "hover:z-20 hover:scale-[1.04] focus-visible:z-20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300",
        tone.bubble,
        active && cn("z-20 scale-[1.06] ring-2", tone.ring),
      )}
      style={{
        left: `${pos.x}%`,
        top: `${pos.y}%`,
        width: size,
        height: size,
        boxShadow: active || item.tone === "growing" ? tone.glow : "0 4px 14px rgba(15,23,42,0.06)",
      }}
    >
      {labelBelow ? (
        <>
          {!item.gap && (
            <>
              <span className="block text-[13px] font-bold tabular-nums leading-none tracking-tight">{item.used}</span>
              <span className="mt-0.5 block text-[9px] font-medium uppercase tracking-wide opacity-60">uses</span>
            </>
          )}
          <span
            className={cn(
              "pointer-events-none absolute left-1/2 top-full mt-2 w-max max-w-[140px] -translate-x-1/2 text-center",
            )}
          >
            <span className={cn("block text-[12px] font-bold leading-tight", item.gap ? "text-red-600" : "text-slate-800")}>
              {item.label}
            </span>
            {item.sublabel && (
              <span className={cn("mt-0.5 block text-[10px]", item.gap ? "text-red-500/90" : "text-slate-500")}>
                {item.sublabel}
              </span>
            )}
          </span>
        </>
      ) : (
        <>
          <span className="block px-1 text-[12px] font-bold leading-snug tracking-[-0.01em]">{item.label}</span>
          {item.sublabel && <span className="mt-0.5 block text-[10px] leading-tight opacity-65">{item.sublabel}</span>}
        </>
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
  /** When provided and non-empty, shows a KPI strip above the map (off by default). */
  businessKpis?: { label: string; value: string; hint: string; honesty: HonestyKind }[];
  mapSubtitle?: string;
  conversations30d?: number[];
  crmWeeks?: { week: string; count: number }[];
  todayHint?: string;
};

export function InvestorsAnalytics({
  agentId,
  bubbles = ANALYTICS_BUBBLES,
  bubblePositions = BUBBLE_POS,
  hubId = "referrals",
  skipLinkIds = ["selling"],
  kicker = "Knowledge block · Investors · Analytics",
  title = "What Investors knows",
  description = "Every bubble is something the block has learned. Size shows how often it is used. Click one to see the evidence.",
  businessKpis,
  mapSubtitle,
  conversations30d = ANALYTICS_CONVERSATIONS_30D,
  crmWeeks = ANALYTICS_CRM_WEEKS,
  todayHint = "The charts already in Creator stay here",
}: KnowledgeAnalyticsProps) {
  const [active, setActive] = useState(bubbles[0]?.id ?? hubId);
  const [rulesMade, setRulesMade] = useState<Set<string>>(() => new Set());
  const bubble = bubbles.find((item) => item.id === active) ?? bubbles[0];
  const analytics = useQuery({
    queryKey: ["agent-analytics", agentId],
    queryFn: () => getAgentAnalytics(agentId!),
    enabled: !!agentId,
  });

  const dayBars = useMemo(
    () => conversations30d.map((v, i) => ({ day: i + 1, count: v })),
    [conversations30d],
  );

  const patternCount = bubbles.length;
  const mapHint = mapSubtitle ?? `Investors block · ${patternCount} patterns · click a bubble`;
  const tone = bubble ? TONE_META[bubble.tone] : TONE_META.growing;
  const hubPos = bubblePositions[hubId] ?? { x: 50, y: 50 };
  const ruleApproved = bubble ? rulesMade.has(bubble.id) || !!bubble.inUse : false;

  const makeRule = () => {
    if (!bubble?.rule) return;
    setRulesMade((prev) => new Set(prev).add(bubble.id));
    addSharedPulseAction({
      title: `Rule · ${bubble.label}`,
      insightTitle: bubble.label,
      source: `${kicker} · ${bubble.source}`,
    });
    toast.success("Marked as a company rule", {
      description: bubble.rule,
      action: {
        label: "Open Pulse",
        onClick: () => {
          window.location.href = "/dashboard?view=insights";
        },
      },
    });
  };

  const coverGap = () => {
    if (!bubble) return;
    addSharedPulseAction({
      title: `Cover gap · ${bubble.label}`,
      insightTitle: bubble.label,
      source: `${kicker} · ${bubble.source}`,
    });
    toast.success("Gap added to action list", {
      description: "Track coverage work on Pulse.",
      action: {
        label: "Open Pulse",
        onClick: () => {
          window.location.href = "/dashboard?view=insights";
        },
      },
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <p className="font-mono text-[10px] tracking-[0.14em] text-cyan-700 uppercase">{kicker}</p>
        <h1
          className="mt-1 text-[24px] font-extrabold tracking-[-0.03em] text-slate-900 sm:text-[28px]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {title}
        </h1>
        <p className="mt-1 max-w-[62ch] text-[13.5px] text-slate-500">{description}</p>
      </div>

      {businessKpis && businessKpis.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {businessKpis.map((kpi) => (
            <div key={kpi.label} className={cn("px-4 py-3.5", CARD)}>
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-[10px] tracking-[0.1em] text-slate-500 uppercase">{kpi.label}</p>
                <HonestyBadge kind={kpi.honesty} className="scale-90" />
              </div>
              <p
                className="mt-1.5 text-[22px] font-extrabold tracking-[-0.03em] text-slate-900"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {kpi.value}
              </p>
              <p className="mt-0.5 truncate text-[12px] text-slate-500">{kpi.hint}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(280px,0.85fr)]">
        <section className={cn("flex flex-col overflow-hidden", CARD)} aria-label="Knowledge map">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
            <div>
              <h2 className="text-[15px] font-semibold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
                Knowledge map
              </h2>
              <p className="text-[12px] text-slate-500">{mapHint}</p>
            </div>
            <HonestyBadge kind="illustrative" />
          </div>

          <div
            className="relative min-h-[400px] flex-1 pb-14 pt-2 sm:min-h-[440px]"
            style={{
              backgroundColor: "#f8fafc",
              backgroundImage:
                "radial-gradient(circle at 46% 48%, rgba(6,182,212,0.09), transparent 42%), radial-gradient(rgba(148,163,184,0.32) 1px, transparent 1px)",
              backgroundSize: "auto, 22px 22px",
            }}
          >
            <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
              {bubbles
                .filter((b) => !skipLinkIds.includes(b.id) && !b.gap)
                .map((item) => {
                  const to = bubblePositions[item.id];
                  if (!to || item.id === hubId) return null;
                  return (
                    <line
                      key={item.id}
                      x1={`${hubPos.x}%`}
                      y1={`${hubPos.y}%`}
                      x2={`${to.x}%`}
                      y2={`${to.y}%`}
                      stroke="rgba(148,163,184,0.28)"
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

          <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-slate-100 px-4 py-3 sm:px-5">
            {LEGEND.map((item) => (
              <span key={item.tone} className="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
                <i className={cn("inline-block size-2.5 rounded-full", TONE_META[item.tone].legend)} aria-hidden />
                {item.label}
              </span>
            ))}
          </div>
        </section>

        {bubble && (
          <aside className={cn("flex flex-col overflow-hidden", CARD)} aria-label="Selected pattern">
            <div className={cn("h-1 w-full")} style={{ background: tone.fill }} />
            <div className="flex flex-1 flex-col p-4 sm:p-5">
              <p className="font-mono text-[10px] tracking-[0.14em] text-cyan-700 uppercase">Selected</p>
              <h2
                className="mt-1 text-[22px] font-extrabold tracking-[-0.02em] text-slate-900"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {bubble.label}
              </h2>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {ruleApproved ? (
                  <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
                    Company rule · in use
                  </span>
                ) : (
                  bubble.strength && (
                    <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", tone.chip)}>
                      {bubble.strength}
                    </span>
                  )
                )}
                {bubble.agent && bubble.agent !== "—" && (
                  <span className="rounded-full bg-sky-50 px-2.5 py-1 text-[11px] font-medium text-sky-700 ring-1 ring-sky-200">
                    {bubble.agent}
                  </span>
                )}
                <HonestyBadge kind={bubble.honesty} className="scale-90" />
              </div>

              <p className="mt-3 text-[13.5px] leading-relaxed text-slate-600">{bubble.summary}</p>

              <div className="mt-4 grid grid-cols-2 gap-2">
                {bubble.stats.map((stat) => (
                  <div key={stat.label} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                    <b
                      className="block text-[16px] font-extrabold tracking-[-0.02em] text-slate-900"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {stat.value}
                    </b>
                    <span className="mt-0.5 block text-[10px] font-medium tracking-[0.04em] text-slate-500 uppercase">
                      {stat.label}
                    </span>
                  </div>
                ))}
              </div>

              <p className="mt-4 text-[12px] leading-relaxed text-slate-500">{bubble.source}</p>

              <div className="mt-auto flex flex-wrap gap-2 pt-5">
                {ruleApproved ? null : (
                  <>
                    {bubble.simulate && (
                      <a
                        href={CLAUDE_SIMULATE_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex min-h-10 flex-1 items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-500 px-3 text-[13px] font-semibold text-white shadow-sm hover:from-cyan-400 hover:to-indigo-400"
                      >
                        <Sparkles className="size-3.5" />
                        Simulate in Claude
                        <ExternalLink className="size-3 opacity-80" />
                      </a>
                    )}
                    {bubble.rule && (
                      <button
                        type="button"
                        onClick={makeRule}
                        className="inline-flex min-h-10 flex-1 items-center justify-center rounded-xl bg-indigo-600 px-3 text-[13px] font-semibold text-white hover:bg-indigo-700"
                      >
                        Make it a rule
                      </button>
                    )}
                    {bubble.workerGap && (
                      <button
                        type="button"
                        onClick={coverGap}
                        className="inline-flex min-h-10 w-full items-center justify-center rounded-xl bg-indigo-600 px-3 text-[13px] font-semibold text-white hover:bg-indigo-700"
                      >
                        Cover this gap
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          </aside>
        )}
      </div>

      <section className={cn("overflow-hidden", CARD)} aria-label="Today's analytics">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
          <div>
            <h2 className="text-[15px] font-semibold text-slate-900" style={{ fontFamily: "var(--font-display)" }}>
              Today&apos;s analytics
            </h2>
            <p className="text-[12px] text-slate-500">{todayHint}</p>
          </div>
          <HonestyBadge kind="illustrative" />
        </div>

        <div className="grid gap-6 p-4 sm:p-5 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-[12px] font-medium text-slate-600">Conversations per day · last 30 days</p>
            <div className="h-[160px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dayBars} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="day" hide />
                  <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={28} />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    cursor={{ fill: "rgba(6,182,212,0.08)" }}
                    formatter={(value) => [Number(value), "Conversations"]}
                    labelFormatter={(label) => `Day ${label}`}
                  />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]} barSize={10}>
                    {dayBars.map((row, i) => (
                      <Cell
                        key={row.day}
                        fill={`rgba(6,182,212,${(0.28 + 0.72 * (i / Math.max(dayBars.length - 1, 1))).toFixed(2)})`}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-1 flex justify-between text-[11px] text-slate-500">
              <span>−30d</span>
              <span>today</span>
            </div>
          </div>

          <div>
            <p className="mb-2 text-[12px] font-medium text-slate-600">Handed to CRM · per week</p>
            <div className="h-[160px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={crmWeeks} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="week" tick={AXIS_TICK} axisLine={false} tickLine={false} />
                  <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={28} allowDecimals={false} />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    cursor={{ fill: "rgba(6,182,212,0.08)" }}
                    formatter={(value) => [Number(value), "Handed to CRM"]}
                  />
                  <Bar dataKey="count" fill="#06b6d4" radius={[6, 6, 0, 0]} barSize={56} label={{ position: "top", fill: "#475569", fontSize: 12, fontWeight: 600 }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </section>

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
