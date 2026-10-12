"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Building2, MessageSquare, BookOpen, Radar } from "lucide-react";
import { cn } from "@qiko/ui";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import type { FocusId, WorkerId } from "@/components/intelligence-layer/model";
import { MAP_EDGES, MAP_LAYOUT, pulseNode, type PulseNode } from "./nodes";

const ICONS = {
  "investor-app": Radar,
  properties: Building2,
  knowledge: BookOpen,
  chat: MessageSquare,
} as const;

const ORDER: FocusId[] = [
  "record",
  "investor-app",
  "properties",
  "intent-intelligence",
  "property-insights",
  "knowledge",
  "chat",
];

export function PulseMap({
  focus,
  workerNames,
  onSelect,
}: {
  focus: FocusId | null;
  workerNames?: Partial<Record<WorkerId, string>>;
  onSelect: (id: FocusId) => void;
}) {
  const [hover, setHover] = useState<FocusId | null>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const gradientId = useId();
  const hovered = hover ? pulseNode(hover, workerNames) : null;

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const sync = () => {
      const box = el.getBoundingClientRect();
      setSize({ w: box.width, h: box.height });
    };
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section aria-label="Company intelligence map" className="rounded-2xl border border-white/10 bg-muted">
      <div className="flex items-start justify-between gap-3 p-4 sm:px-5 sm:pt-5">
        <div>
          <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
            Knowledge map
          </h2>
          <p className="mt-0.5 text-[12px] text-slate-500">Hover for a summary. Click a block or worker to open it.</p>
        </div>
        <HonestyBadge kind="illustrative" />
      </div>

      <div className="space-y-2 px-4 pb-4 md:hidden">
        {ORDER.map((id) => {
          const node = pulseNode(id, workerNames);
          return (
            <button
              key={id}
              type="button"
              onClick={() => onSelect(id)}
              className={cn(
                "flex min-h-11 w-full flex-col rounded-xl border bg-card px-3 py-3 text-left",
                focus === id ? "border-primary" : "border-white/10",
              )}
            >
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-slate-500">{node.kicker}</span>
              <span className="mt-0.5 text-[14px] font-semibold text-foreground">{node.name}</span>
              <span className="mt-1 text-[12.5px] text-slate-400">{node.summary}</span>
            </button>
          );
        })}
      </div>

      <div ref={canvas} className="relative hidden min-h-[520px] md:block">
        <div
          className="pointer-events-none absolute inset-3 rounded-xl"
          style={{
            backgroundImage: "radial-gradient(circle at 1px 1px, rgba(255,255,255,.08) 1.1px, transparent 0)",
            backgroundSize: "22px 22px",
          }}
        />
        {size.w > 0 && (
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
          viewBox={`0 0 ${size.w} ${size.h}`}
          aria-hidden="true"
        >
          <defs>
            <linearGradient id={gradientId} x1="0" x2="1">
              <stop offset="0" stopColor="#6366F1" />
              <stop offset="1" stopColor="#22D3EE" />
            </linearGradient>
          </defs>
          {MAP_EDGES.map(([from, to], index) => {
            const edge = curvePath(xy(from, size), xy(to, size), bendFor(from, to));
            const active = !focus || focus === from || focus === to;
            const toCore = from === "record" || to === "record";
            return (
              <g key={`${from}-${to}`} opacity={active ? 1 : 0.28}>
                <path
                  d={edge}
                  fill="none"
                  stroke={active ? `url(#${gradientId})` : "rgba(255,255,255,0.16)"}
                  strokeWidth={toCore ? 1.2 : 1.35}
                  strokeOpacity={toCore ? 0.32 : 0.2}
                />
                <path
                  d={edge}
                  className={toCore ? "pulse-flowline pulse-flowline-fast" : "pulse-flowline"}
                  stroke={toCore ? "#22D3EE" : "#6366F1"}
                  strokeOpacity={active ? 0.72 : 0.22}
                />
                <circle r="2.3" fill={toCore ? "#22D3EE" : "#A5B4FC"} className="pulse-dot">
                  <animateMotion dur={`${2.2 + (index % 4) * 0.35}s`} repeatCount="indefinite" begin={`${(index % 5) * 0.28}s`} path={edge} />
                </circle>
                <circle r="1.6" fill="#22D3EE" className="pulse-dot" opacity="0.75">
                  <animateMotion dur={`${2.8 + (index % 3) * 0.4}s`} repeatCount="indefinite" begin={`${0.9 + (index % 4) * 0.22}s`} path={edge} />
                </circle>
              </g>
            );
          })}
        </svg>
        )}

        {ORDER.map((id) => {
          const node = pulseNode(id, workerNames);
          const pos = MAP_LAYOUT[id];
          const dimmed = Boolean(focus && focus !== id && !connectedTo(focus, id));
          return (
            <MapNode
              key={id}
              node={node}
              left={pos.x}
              top={pos.y}
              selected={focus === id}
              dimmed={dimmed}
              onSelect={() => onSelect(id)}
              onHover={setHover}
            />
          );
        })}

        {hovered && (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-20 w-[240px] rounded-xl border border-white/10 bg-popover px-3.5 py-3 shadow-[0_16px_40px_-16px_rgba(0,0,0,.55)]"
            style={{
              left: MAP_LAYOUT[hovered.id].x,
              top: MAP_LAYOUT[hovered.id].y,
              transform: hovered.id === "record" || hovered.kind === "block"
                ? "translate(-50%, calc(-100% - 36px))"
                : "translate(-50%, calc(-100% - 20px))",
            }}
          >
            <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500">{hovered.kicker}</p>
            <p className="mt-1 text-[14px] font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{hovered.name}</p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-slate-400">{hovered.summary}</p>
            <p className="mt-2 text-[12px] font-semibold text-primary">Click to open →</p>
          </div>
        )}
      </div>
    </section>
  );
}

function MapNode({
  node,
  left,
  top,
  selected,
  dimmed,
  onSelect,
  onHover,
}: {
  node: PulseNode;
  left: string;
  top: string;
  selected: boolean;
  dimmed: boolean;
  onSelect: () => void;
  onHover: (id: FocusId | null) => void;
}) {
  const Icon = node.kind === "block" || node.kind === "source" ? ICONS[node.id as keyof typeof ICONS] : null;
  return (
    <button
      type="button"
      aria-pressed={selected}
      aria-label={`${node.kicker}: ${node.name}`}
      onClick={onSelect}
      onMouseEnter={() => onHover(node.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(node.id)}
      onBlur={() => onHover(null)}
      className={cn(
        "absolute z-10 -translate-x-1/2 -translate-y-1/2 text-left transition duration-150 motion-reduce:transition-none",
        dimmed && "opacity-35",
      )}
      style={{ left, top }}
    >
      {node.kind === "record" ? (
        <span
          className={cn(
            "relative flex size-[128px] flex-col items-center justify-center rounded-full text-center",
            selected && "ring-4 ring-primary/20",
          )}
        >
          <span className="absolute inset-0 rounded-full bg-indigo-500/15 motion-safe:animate-[qiko-breathe_2.4s_ease-in-out_infinite]" />
          <span className="absolute inset-[-10px] rounded-full border border-violet-400/25 motion-safe:animate-[qiko-breathe_2.4s_ease-in-out_infinite]" />
          <span className="relative flex size-[88px] flex-col items-center justify-center rounded-full bg-gradient-to-br from-[#6366F1] to-[#22D3EE] text-white shadow-[0_10px_24px_-10px_rgba(99,102,241,.55)]">
            <span className="text-[9px] font-medium uppercase tracking-[0.14em] text-white/80">Company</span>
            <span className="mt-0.5 px-2 text-[13px] font-extrabold leading-tight" style={{ fontFamily: "var(--font-display)" }}>{node.name}</span>
          </span>
        </span>
      ) : node.kind === "worker" ? (
        <span
          className={cn(
            "flex w-[168px] flex-col rounded-2xl border bg-card px-3 py-3 shadow-[0_1px_3px_rgba(0,0,0,.35)]",
            selected ? "border-primary ring-4 ring-primary/10" : "border-white/10 hover:border-primary/40",
          )}
        >
          <span className="text-[9.5px] font-medium uppercase tracking-[0.1em] text-primary">Worker</span>
          <span className="mt-1 text-[14px] font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{node.name}</span>
        </span>
      ) : (
        <span
          className={cn(
            "flex items-center gap-2 rounded-full border bg-card px-3 py-2 shadow-[0_1px_3px_rgba(0,0,0,.35)]",
            node.kind === "source" ? "min-w-0" : "min-w-[132px]",
            selected ? "border-primary ring-4 ring-primary/10" : "border-white/10 hover:border-primary/40",
          )}
        >
          {Icon && <Icon className="size-3.5 shrink-0 text-primary" />}
          <span>
            <span className="block text-[13px] font-semibold text-foreground">{node.name}</span>
            {node.kind === "block" && <span className="block text-[11px] text-slate-500">{node.kicker}</span>}
          </span>
        </span>
      )}
    </button>
  );
}

function connectedTo(focus: FocusId, id: FocusId) {
  return MAP_EDGES.some(([from, to]) => (from === focus && to === id) || (to === focus && from === id));
}

function xy(id: FocusId, size: { w: number; h: number }) {
  return {
    x: (Number.parseFloat(MAP_LAYOUT[id].x) / 100) * size.w,
    y: (Number.parseFloat(MAP_LAYOUT[id].y) / 100) * size.h,
  };
}

function bendFor(from: FocusId, to: FocusId) {
  if (from === "record" || to === "record") return -0.12;
  if (from === "knowledge" || from === "chat" || to === "knowledge" || to === "chat") return 0.18;
  return 0.1;
}

function curvePath(a: { x: number; y: number }, b: { x: number; y: number }, bend: number) {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const cx = mx - (b.y - a.y) * bend;
  const cy = my + (b.x - a.x) * bend;
  return `M ${a.x.toFixed(1)} ${a.y.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
}
