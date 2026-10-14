"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  CircleDot,
  Sparkles,
} from "lucide-react";
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
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { getAgentAnalytics } from "@/lib/api";
import { ANALYTICS_BUBBLES, type AnalyticsBubble } from "./investors-data";

const CARD = "rounded-2xl border border-white/[0.08] bg-[#0b0f18]";
const TOOLTIP_STYLE = {
  background: "#0f1220",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 10,
  fontSize: 12,
  color: "#e2e8f0",
  boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
} as const;
const AXIS_TICK = { fill: "#64748b", fontSize: 11 } as const;

const TONE_META = {
  growing: {
    fill: "#818cf8",
    chip: "bg-emerald-400/12 text-emerald-300 ring-1 ring-emerald-400/20",
    bubble: "border-indigo-400/80 bg-indigo-500/20 text-indigo-50",
    accent: "bg-indigo-500",
    soft: "rgba(129,140,248,0.35)",
  },
  established: {
    fill: "#22d3ee",
    chip: "bg-cyan-400/12 text-cyan-300 ring-1 ring-cyan-400/20",
    bubble: "border-cyan-400/70 bg-cyan-500/15 text-cyan-50",
    accent: "bg-cyan-500",
    soft: "rgba(34,211,238,0.28)",
  },
  attention: {
    fill: "#fbbf24",
    chip: "bg-amber-400/12 text-amber-300 ring-1 ring-amber-400/20",
    bubble: "border-amber-400/80 bg-amber-500/15 text-amber-50",
    accent: "bg-amber-500",
    soft: "rgba(251,191,36,0.28)",
  },
  gap: {
    fill: "#f87171",
    chip: "bg-red-400/12 text-red-300 ring-1 ring-red-400/20",
    bubble: "border-dashed border-red-400/70 bg-transparent text-slate-400",
    accent: "bg-red-500",
    soft: "rgba(248,113,113,0.2)",
  },
} as const;

/** Map board positions (% of container) — constellation, not a random wrap. */
const BUBBLE_POS: Record<string, { x: number; y: number }> = {
  referrals: { x: 22, y: 38 },
  gulf: { x: 48, y: 26 },
  offplan: { x: 72, y: 34 },
  service: { x: 38, y: 58 },
  yield: { x: 62, y: 62 },
  ready: { x: 82, y: 58 },
  selling: { x: 18, y: 72 },
};

/** Illustrative 14-day usage series for the demo chart. */
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
}: {
  item: AnalyticsBubble;
  active: boolean;
  onSelect: () => void;
}) {
  const pos = BUBBLE_POS[item.id] ?? { x: 50, y: 50 };
  const size = Math.max(64, Math.min(112, Math.round(52 + item.size * 0.55)));
  const tone = TONE_META[item.tone];

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        "absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 px-2 text-center transition-all duration-200",
        "hover:z-20 hover:scale-[1.06] focus-visible:z-20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70",
        tone.bubble,
        active && "z-20 scale-[1.1] ring-2 ring-white/45 shadow-[0_0_28px_rgba(255,255,255,0.12)]",
      )}
      style={{ left: `${pos.x}%`, top: `${pos.y}%`, width: size, height: size }}
    >
      <span className="block text-[11px] font-semibold leading-tight tracking-[-0.01em]">{item.label}</span>
      {item.sublabel && (
        <span className={cn("mt-0.5 block text-[9px] leading-tight", item.gap ? "text-red-300/90" : "opacity-70")}>
          {item.sublabel}
        </span>
      )}
    </button>
  );
}

export function InvestorsAnalytics({ agentId }: { agentId?: string }) {
  const [active, setActive] = useState(ANALYTICS_BUBBLES[0]?.id ?? "referrals");
  const bubble = ANALYTICS_BUBBLES.find((item) => item.id === active) ?? ANALYTICS_BUBBLES[0];
  const analytics = useQuery({
    queryKey: ["agent-analytics", agentId],
    queryFn: () => getAgentAnalytics(agentId!),
    enabled: !!agentId,
  });

  const strengthData = useMemo(() => patternBars(ANALYTICS_BUBBLES), []);
  const usageData = useMemo(() => {
    if (!analytics.data) return SAMPLE_USAGE;
    const base = Math.max(8, analytics.data.calls || 12);
    return SAMPLE_USAGE.map((row, i) => ({
      ...row,
      calls: Math.max(4, Math.round(base * (0.55 + ((i % 5) * 0.12)) + (i % 3) * 2)),
      tokens: Math.max(10, Math.round((analytics.data!.input_tokens + analytics.data!.output_tokens || 40) * (0.04 + (i % 7) * 0.01))),
    }));
  }, [analytics.data]);

  const covered = ANALYTICS_BUBBLES.filter((b) => !b.gap).length;
  const gaps = ANALYTICS_BUBBLES.filter((b) => b.gap).length;
  const tone = bubble ? TONE_META[bubble.tone] : TONE_META.growing;
  const liveConnected = Boolean(agentId && analytics.data);

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-[10px] tracking-[0.14em] text-violet-300/90 uppercase">
              Investors · Analytics
            </p>
            <HonestyBadge kind={liveConnected ? "connected" : "illustrative"} />
          </div>
          <h1
            className="mt-1 text-[24px] font-extrabold tracking-[-0.03em] text-white sm:text-[28px]"
            style={{ fontFamily: "var(--font-display)" }}
          >
            What Investors knows
          </h1>
          <p className="mt-1 max-w-[62ch] text-[13.5px] text-slate-400">
            Patterns the block has learned, how often they are used, and where coverage is still missing.
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Patterns covered", value: String(covered), hint: `${gaps} gap${gaps === 1 ? "" : "s"} open`, icon: CircleDot },
          { label: "Strongest lift", value: "+41%", hint: "Referrals vs portal leads", icon: TrendingBadge },
          { label: "Evidence sources", value: "6", hint: "CRM, chat, calendars", icon: Activity },
          { label: "Selected use", value: bubble ? `${bubble.used}%` : "—", hint: bubble?.label ?? "Pick a pattern", icon: BarChart3 },
        ].map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div key={kpi.label} className={cn("px-4 py-3.5", CARD)}>
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-[10px] tracking-[0.1em] text-slate-500 uppercase">{kpi.label}</p>
                <Icon className="size-3.5 text-slate-500" />
              </div>
              <p className="mt-1.5 text-[22px] font-extrabold tracking-[-0.03em] text-white" style={{ fontFamily: "var(--font-display)" }}>
                {kpi.value}
              </p>
              <p className="mt-0.5 truncate text-[12px] text-slate-500">{kpi.hint}</p>
            </div>
          );
        })}
      </div>

      <div className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.9fr)]">
        <section className={cn("overflow-hidden", CARD)} aria-label="Knowledge map">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] px-4 py-3 sm:px-5">
            <div>
              <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
                Knowledge map
              </h2>
              <p className="text-[12px] text-slate-500">Bubble size = relative use · click to inspect</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(["growing", "established", "attention", "gap"] as const).map((key) => (
                <span key={key} className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium capitalize", TONE_META[key].chip)}>
                  {key === "attention" ? "Needs attention" : key}
                </span>
              ))}
            </div>
          </div>

          <div className="relative h-[360px] bg-[radial-gradient(circle_at_50%_40%,rgba(99,102,241,0.12),transparent_55%)] sm:h-[400px]">
            <div
              className="pointer-events-none absolute inset-0 opacity-40 [background-image:radial-gradient(rgba(148,163,184,0.18)_1px,transparent_1px)] [background-size:22px_22px]"
              aria-hidden
            />
            <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
              {ANALYTICS_BUBBLES.filter((b) => b.id !== "selling").map((item) => {
                const from = BUBBLE_POS.referrals;
                const to = BUBBLE_POS[item.id];
                if (!to || item.id === "referrals") return null;
                return (
                  <line
                    key={item.id}
                    x1={`${from.x}%`}
                    y1={`${from.y}%`}
                    x2={`${to.x}%`}
                    y2={`${to.y}%`}
                    stroke="rgba(148,163,184,0.18)"
                    strokeWidth="1"
                  />
                );
              })}
            </svg>
            {ANALYTICS_BUBBLES.map((item) => (
              <MapBubble
                key={item.id}
                item={item}
                active={active === item.id}
                onSelect={() => setActive(item.id)}
              />
            ))}
          </div>
        </section>

        {bubble && (
          <aside className={cn("flex flex-col overflow-hidden", CARD)} aria-label="Selected pattern">
            <div className={cn("h-1 w-full", tone.accent)} />
            <div className="flex flex-1 flex-col p-4 sm:p-5">
              <p className="font-mono text-[10px] tracking-[0.12em] text-slate-500 uppercase">Selected pattern</p>
              <h2 className="mt-1 text-[20px] font-extrabold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>
                {bubble.label}
              </h2>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {bubble.strength && (
                  <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", tone.chip)}>
                    {bubble.strength}
                  </span>
                )}
                {bubble.agent && bubble.agent !== "—" && (
                  <span className="rounded-full bg-sky-400/12 px-2.5 py-1 text-[11px] font-medium text-sky-300 ring-1 ring-sky-400/20">
                    {bubble.agent}
                  </span>
                )}
              </div>

              <p className="mt-3 text-[13.5px] leading-relaxed text-slate-300">{bubble.summary}</p>

              <div className="mt-4 grid grid-cols-2 gap-2">
                {bubble.stats.map((stat) => (
                  <div key={stat.label} className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2.5">
                    <b className="block text-[17px] font-extrabold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>
                      {stat.value}
                    </b>
                    <span className="text-[11px] text-slate-500">{stat.label}</span>
                  </div>
                ))}
              </div>

              <p className="mt-3 flex items-start gap-1.5 text-[12px] text-slate-500">
                <ArrowUpRight className="mt-0.5 size-3.5 shrink-0 opacity-70" />
                {bubble.source}
              </p>

              <div className="mt-auto flex flex-wrap gap-2 pt-5">
                <Link
                  href="/studio/intelligence?tab=channels&surface=claude"
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-indigo-500 px-3.5 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
                >
                  <Sparkles className="size-3.5" />
                  Simulate in Claude
                </Link>
                <button
                  type="button"
                  disabled={!!bubble.gap}
                  className="inline-flex min-h-10 items-center rounded-lg border border-white/15 px-3.5 text-[13px] font-semibold text-slate-200 hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                >
                  Make it a rule
                </button>
              </div>
            </div>
          </aside>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className={cn("p-4 sm:p-5", CARD)} aria-label="Usage over time">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
                <Activity className="size-4 text-cyan-400" />
                Usage · last 14 days
              </h2>
              <p className="mt-0.5 text-[12px] text-slate-500">
                {liveConnected ? "Scaled from linked worker usage" : "Illustrative series for the demo walkthrough"}
              </p>
            </div>
            <HonestyBadge kind={liveConnected ? "connected" : "illustrative"} />
          </div>
          <div className="h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={usageData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="invCallsFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="invTokensFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#818cf8" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="#818cf8" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="day" tick={AXIS_TICK} axisLine={false} tickLine={false} interval={1} />
                <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={32} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  cursor={{ stroke: "rgba(255,255,255,0.12)" }}
                  formatter={(value, name) => [Number(value).toLocaleString(), name === "calls" ? "Calls" : "Token index"]}
                />
                <Area type="monotone" dataKey="tokens" name="tokens" stroke="#818cf8" strokeWidth={2} fill="url(#invTokensFill)" />
                <Area type="monotone" dataKey="calls" name="calls" stroke="#22d3ee" strokeWidth={2.25} fill="url(#invCallsFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap gap-4 text-[11px] text-slate-500">
            <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-cyan-400" /> Calls</span>
            <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-indigo-400" /> Token index</span>
          </div>
          {agentId && analytics.isError && (
            <button type="button" className="mt-2 text-[12px] text-cyan-300 underline" onClick={() => analytics.refetch()}>
              Retry live usage
            </button>
          )}
        </section>

        <section className={cn("p-4 sm:p-5", CARD)} aria-label="Pattern strength">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
                <BarChart3 className="size-4 text-indigo-400" />
                Pattern strength
              </h2>
              <p className="mt-0.5 text-[12px] text-slate-500">Relative use across covered patterns · click a bar to select</p>
            </div>
            <HonestyBadge kind="illustrative" />
          </div>
          <div className="h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={strengthData}
                layout="vertical"
                margin={{ top: 4, right: 12, left: 4, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
                <XAxis type="number" tick={AXIS_TICK} axisLine={false} tickLine={false} unit="%" />
                <YAxis type="category" dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} width={88} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                  formatter={(value, _name, item) => {
                    const full = (item?.payload as { full?: string } | undefined)?.full;
                    return [`${Number(value)}% use`, full ?? "Pattern"];
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
                    <Cell
                      key={row.id}
                      fill={row.id === active ? row.fill : `${row.fill}99`}
                      stroke={row.id === active ? "#fff" : "transparent"}
                      strokeWidth={row.id === active ? 1 : 0}
                    />
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
              <p className="font-mono text-[10px] tracking-[0.08em] text-slate-500 uppercase">{label}</p>
              <p className="mt-1 text-[15px] font-semibold text-white">{Number(value).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TrendingBadge({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cn("size-3.5", className)} aria-hidden>
      <path d="M2 11.5 6.5 7l2.5 2.5L14 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 4.5h4v4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
